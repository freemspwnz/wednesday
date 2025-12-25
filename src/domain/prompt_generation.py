"""Доменный сервис для генерации промптов.

Содержит чистую логику генерации промптов без зависимостей от инфраструктуры
(кэш, файловое хранилище, база данных).
"""

from __future__ import annotations

import random

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
        Выбирает случайный промпт и стиль из переданной конфигурации.

        Returns:
            Валидированный статический промпт для генерации изображения.

        Raises:
            PromptGenerationError: Если конфигурация не предоставлена или fallback промпт невалиден.
        """
        if not self._fallback_config:
            raise PromptGenerationError(
                "Fallback config is required. Provide PromptFallbackConfig during initialization."
            )

        try:
            if not self._fallback_config.frog_prompts or not self._fallback_config.styles:
                fallback_text = self._fallback_config.default_fallback_prompt
            else:
                frog_prompt = random.choice(self._fallback_config.frog_prompts)
                style = random.choice(self._fallback_config.styles)
                fallback_text = f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"

            # Валидация fallback промпта
            return Prompt(fallback_text)
        except ValueError as exc:
            raise PromptGenerationError(f"Невалидный fallback промпт: {exc}") from exc
