"""Доменный сервис для генерации промптов.

Содержит чистую логику генерации промптов без зависимостей от инфраструктуры
(кэш, файловое хранилище, база данных).
"""

from __future__ import annotations

from domain.fallback_prompt_builder import FallbackPromptBuilder
from domain.value_objects import Prompt
from shared.base.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    NetworkError,
    PromptGenerationError,
)
from shared.config import PromptFallbackConfig
from shared.protocols import ITextToTextClient


class PromptGenerationService:
    """Доменный сервис для генерации промптов.

    Выполняет чистую генерацию промптов через ITextToTextClient с fallback
    на статический промпт. Не зависит от инфраструктуры (кэш, файлы, БД).
    """

    def __init__(
        self,
        text_client: ITextToTextClient | None = None,
        fallback_config: PromptFallbackConfig | None = None,
    ) -> None:
        """Инициализирует сервис генерации промптов.

        Args:
            text_client: Клиент для генерации текста (опционально). Если None,
                метод generate() будет бросать PromptGenerationError.
            fallback_config: Конфигурация для fallback промптов (опционально).
                Если None, метод get_fallback_prompt() будет бросать PromptGenerationError.
        """
        self._text_client = text_client
        self._fallback_config = fallback_config

    async def generate(self) -> Prompt:
        """Генерирует промпт для генерации изображения.

        Выполняет генерацию через ITextToTextClient с валидацией результата.

        Returns:
            Валидированный Prompt.

        Raises:
            PromptGenerationError: При ошибках генерации промпта (ошибки клиента,
                ошибки валидации, неожиданные ошибки).
        """
        if self._text_client is None:
            raise PromptGenerationError("Text client is not available")

        try:
            prompt_text = await self._text_client.generate("prompt_for_kandinsky")
            # Валидация промпта сразу после получения от клиента
            return Prompt(prompt_text)

        except (AuthenticationError, NetworkError, APIError, ClientError) as exc:
            # Ошибки клиента → оборачиваем в доменное исключение
            raise PromptGenerationError(f"Ошибка клиента при генерации промпта: {exc}") from exc
        except ValueError as exc:
            # Ошибка валидации промпта
            raise PromptGenerationError(f"Невалидный промпт от клиента: {exc}") from exc
        except (MemoryError, SystemExit, KeyboardInterrupt):
            # Системные ошибки пробрасываем без обработки
            raise
        except Exception as exc:
            # Неожиданные ошибки → оборачиваем в доменное исключение
            raise PromptGenerationError(f"Неожиданная ошибка при генерации промпта: {exc}") from exc

    def get_fallback_prompt(self) -> Prompt:
        """Возвращает статический промпт из конфигурации (fallback).

        Используется когда не удалось получить промпт через текстовый клиент.
        Делегирует построение промпта FallbackPromptBuilder.

        Returns:
            Валидированный статический промпт для генерации изображения.

        Raises:
            PromptGenerationError: Если конфигурация не предоставлена или fallback промпт невалиден.
        """
        if not self._fallback_config:
            raise PromptGenerationError(
                "Обязательное поле конфигурации fallback промпта. Передайте PromptFallbackConfig при инициализации."
            )

        try:
            return FallbackPromptBuilder.build(
                frog_prompts=self._fallback_config.frog_prompts,
                styles=self._fallback_config.styles,
                default_fallback=self._fallback_config.default_fallback_prompt,
            )
        except ValueError as exc:
            raise PromptGenerationError(f"Невалидный fallback промпт: {exc}") from exc
