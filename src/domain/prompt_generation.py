"""Доменный сервис для генерации промптов.

Содержит чистую логику генерации промптов без зависимостей от инфраструктуры
(кэш, файловое хранилище, база данных).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto

from shared.base.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    NetworkError,
)
from shared.config import PromptFallbackConfig
from shared.protocols import ITextToTextClient


class PromptSource(Enum):
    """Источник промпта для генерации изображения."""

    AI = auto()
    FALLBACK_REQUIRED = auto()
    UNAVAILABLE = auto()


@dataclass
class PromptGenerationResult:
    """Результат генерации промпта с указанием источника."""

    prompt: str | None
    source: PromptSource


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
                используется только статический fallback.
            fallback_config: Конфигурация для fallback промптов (опционально).
                Если None, используется дефолтный промпт из PromptFallbackConfig.
        """
        self._text_client = text_client
        self._fallback_config = fallback_config

    async def generate(self) -> PromptGenerationResult:
        """Генерирует промпт для генерации изображения.

        Выполняет генерацию через ITextToTextClient. При ожидаемых ошибках клиента
        возвращает результат с источником FALLBACK_REQUIRED, сигнализируя о необходимости
        использовать статический fallback в вызывающем коде.

        Returns:
            Результат генерации промпта с указанием источника.

        Raises:
            Exception: Неожиданные ошибки пробрасываются дальше для обработки в app-слое.

        Note:
            Ожидаемые ошибки клиента (AuthenticationError, NetworkError, APIError, ClientError)
            обрабатываются и возвращают результат с источником FALLBACK_REQUIRED.
            Неожиданные ошибки пробрасываются для корректной обработки в app-слое.
        """
        if self._text_client is None:
            return PromptGenerationResult(
                prompt=None,
                source=PromptSource.UNAVAILABLE,
            )

        try:
            prompt = await self._text_client.generate("prompt_for_kandinsky")
            return PromptGenerationResult(prompt=prompt, source=PromptSource.AI)

        except (AuthenticationError, NetworkError, APIError, ClientError):
            # Ожидаемые ошибки клиента → используем fallback
            return PromptGenerationResult(
                prompt=None,
                source=PromptSource.FALLBACK_REQUIRED,
            )

    def get_fallback_prompt(self) -> str:
        """Возвращает статический промпт из конфигурации (fallback).

        Используется когда не удалось получить промпт через текстовый клиент.
        Выбирает случайный промпт и стиль из переданной конфигурации.

        Returns:
            Статический промпт для генерации изображения.
        """
        if not self._fallback_config or not self._fallback_config.frog_prompts or not self._fallback_config.styles:
            # Fallback на дефолтный промпт из конфига, если конфигурация не предоставлена или пуста
            if self._fallback_config:
                return self._fallback_config.default_fallback_prompt

            return PromptFallbackConfig(
                frog_prompts=[],
                styles=[],
            ).default_fallback_prompt

        frog_prompt = random.choice(self._fallback_config.frog_prompts)
        style = random.choice(self._fallback_config.styles)
        return f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"
