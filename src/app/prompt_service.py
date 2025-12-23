"""Application service для координации генерации промптов.

Координирует работу доменных и инфраструктурных сервисов для генерации
и кэширования промптов через протокол `ICache`.
"""

from __future__ import annotations

from domain.prompt_generation import (
    PromptGenerationService,
    PromptSource,
)
from shared.base.base_service import BaseService
from shared.base.exceptions import CacheError, PromptGenerationError, UnexpectedPromptError
from shared.protocols import ICache, ILogger


class PromptService(BaseService):
    """Application service для координации генерации промптов.

    Координирует работу:
    - PromptGenerationService (генерация);
    - кэша промптов, удовлетворяющего протоколу ``ICache[dict | str]``.
    """

    def __init__(
        self,
        prompt_generation_service: PromptGenerationService,
        prompt_cache: ICache[dict | str] | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис координации промптов.

        Args:
            prompt_generation_service: Сервис генерации промптов (обязателен).
            prompt_cache: Кэш промптов, реализующий ``ICache[dict | str]`` (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._generation_service = prompt_generation_service
        self._cache = prompt_cache

    async def generate(self) -> str | None:
        """Генерирует промпт с полной координацией всех сервисов.

        Выполняет следующую последовательность:
        1. Проверяет кэш (если доступен)
        2. Генерирует промпт через PromptGenerationService
        3. Сохраняет в кэш (если доступен)
        4. Возвращает промпт или None

        Returns:
            Сгенерированный промпт или None, если генерация не удалась.

        Note:
            При ошибках на любом этапе логирование выполняется, но генерация
            продолжается (graceful degradation).
        """
        # Пытаемся получить промпт из кэша
        if self._cache is not None:
            try:
                cached = await self._cache.get("latest")
                if cached:
                    self.logger.info(
                        "Промпт получен из кэша",
                        event="prompt_cache_hit",
                        status="cached",
                    )
                    return str(cached) if not isinstance(cached, dict) else cached.get("text", str(cached))
            except CacheError as e:
                self.logger.warning(
                    f"Ошибка при получении промпта из кэша: {e}",
                    event="cache_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        # Генерируем новый промпт
        self.logger.info(
            "Начинаю генерацию нового промпта",
            event="prompt_generation_started",
            status="started",
        )

        try:
            result = await self._generation_service.generate()
            if result.source == PromptSource.AI and result.prompt is not None:
                self.logger.info(
                    f"Промпт успешно сгенерирован: {result.prompt[:100]}...",
                    event="prompt_generation_success",
                    status="success",
                )
                prompt = result.prompt
            elif result.source == PromptSource.FALLBACK_REQUIRED:
                self.logger.warning(
                    "Ошибка клиента при генерации промпта, требуется fallback",
                    event="prompt_generation_client_error",
                    status="error",
                )
                prompt = None
            elif result.source == PromptSource.UNAVAILABLE:
                self.logger.warning(
                    "Текстовый клиент недоступен, требуется fallback",
                    event="prompt_generation_unavailable",
                    status="warning",
                )
                prompt = None
            else:
                prompt = None
        except PromptGenerationError as e:
            # Доменное исключение генерации промптов
            unexpected_error = UnexpectedPromptError(
                f"Error while generating prompt: {e}",
                original_error=e,
            )
            self.logger.error(
                f"Ошибка при генерации промпта через domain сервис: {unexpected_error}",
                event="prompt_generation_failed",
                status="error",
                error_type=type(unexpected_error).__name__,
                error_message=str(unexpected_error),
            )
            raise unexpected_error from e
        except Exception as e:
            # Другие неожиданные ошибки
            unexpected_error = UnexpectedPromptError(
                f"Unexpected error while generating prompt: {e}",
                original_error=e,
            )
            self.logger.error(
                f"Неожиданная ошибка при генерации промпта через domain сервис: {unexpected_error}",
                event="prompt_generation_failed",
                status="error",
                error_type=type(unexpected_error).__name__,
                error_message=str(unexpected_error),
            )
            raise unexpected_error from e

        if prompt is None:
            # Используем статический fallback
            self.logger.info(
                "Начинаю получение fallback промпта",
                event="prompt_fallback_started",
                status="started",
            )
            try:
                prompt = self._generation_service.get_fallback_prompt()
                self.logger.warning(
                    "Использован статический fallback-промпт",
                    event="prompt_fallback_used",
                    status="fallback",
                )
            except Exception as e:
                # Неожиданная ошибка при получении статического fallback‑промпта
                unexpected_error = UnexpectedPromptError(
                    f"Unexpected error while getting fallback prompt: {e}",
                    original_error=e,
                )
                self.logger.error(
                    f"Ошибка при получении fallback промпта: {unexpected_error}",
                    event="prompt_fallback_failed",
                    status="error",
                    error_type=type(unexpected_error).__name__,
                    error_message=str(unexpected_error),
                )
                return None

        # Сохраняем в кэш (если доступен)
        if prompt and self._cache is not None:
            try:
                await self._cache.set("latest", prompt)
                self.logger.debug(
                    "Промпт сохранён в кэш",
                    event="prompt_cached",
                    status="cached",
                )
            except CacheError as e:
                self.logger.warning(
                    f"Ошибка при сохранении промпта в кэш: {e}",
                    event="cache_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        return prompt
