"""Application service для координации генерации промптов.

Координирует работу доменных и инфраструктурных сервисов для генерации
и кэширования промптов через протокол `ICache`.
"""

from __future__ import annotations

from services.base.base_service import BaseService
from services.domain.prompt_generation import PromptGenerationService
from services.infrastructure.cache.prompt_cache import PromptCache
from services.protocols import ICache


class PromptService(BaseService):
    """Application service для координации генерации промптов.

    Координирует работу:
    - PromptGenerationService (генерация);
    - кэша промптов, удовлетворяющего протоколу ``ICache[dict | str]``.
    """

    def __init__(
        self,
        prompt_generation_service: PromptGenerationService,
        prompt_cache: PromptCache | ICache[dict | str] | None = None,
    ) -> None:
        """Инициализирует сервис координации промптов.

        Args:
            prompt_generation_service: Сервис генерации промптов (обязателен).
            prompt_cache: Кэш промптов, реализующий ``ICache[dict | str]`` (опционально).
        """
        super().__init__()
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
                    self.log_event(
                        event="prompt_cache_hit",
                        status="cached",
                        level="info",
                        message="Промпт получен из кэша",
                    )
                    return str(cached) if not isinstance(cached, dict) else cached.get("text", str(cached))
            except Exception as e:
                self.logger.warning(f"Ошибка при получении промпта из кэша: {e}")

        # Генерируем новый промпт
        self.log_event(
            event="prompt_generation_started",
            status="started",
            level="info",
            message="Начинаю генерацию нового промпта",
        )

        prompt = await self._generation_service.generate()

        if prompt is None:
            # Используем статический fallback
            prompt = self._generation_service.get_fallback_prompt()
            self.log_event(
                event="prompt_fallback_used",
                status="fallback",
                level="warning",
                message="Использован статический fallback-промпт",
            )

        # Сохраняем в кэш (если доступен)
        if prompt and self._cache is not None:
            try:
                await self._cache.set("latest", prompt)
                self.log_event(
                    event="prompt_cached",
                    status="cached",
                    level="debug",
                    message="Промпт сохранён в кэш",
                )
            except Exception as e:
                self.logger.warning(f"Ошибка при сохранении промпта в кэш: {e}")

        return prompt
