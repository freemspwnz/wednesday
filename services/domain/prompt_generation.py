"""Доменный сервис для генерации промптов.

Содержит чистую логику генерации промптов без зависимостей от инфраструктуры
(кэш, файловое хранилище, база данных).
"""

from __future__ import annotations

import random

from services.base.base_service import BaseService
from services.domain.prompt_fallback_config import PromptFallbackConfig
from services.protocols import ITextToTextClient


class PromptGenerationService(BaseService):
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
        """
        super().__init__()
        self._text_client = text_client
        self._fallback_config = fallback_config

    async def generate(self) -> str | None:
        """Генерирует промпт для генерации изображения.

        Выполняет генерацию через ITextToTextClient. При ошибке или пустом
        ответе возвращает None, что сигнализирует о необходимости использовать
        статический fallback в вызывающем коде.

        Returns:
            Сгенерированный промпт или None, если генерация не удалась.

        Raises:
            PromptGenerationError: При критических ошибках генерации.
        """
        if self._text_client is None:
            self.log_event(
                event="prompt_generation_skipped",
                status="no_client",
                level="info",
                message="Текстовый клиент не настроен, используем статический fallback",
            )
            return None

        try:
            self.log_event(
                event="prompt_generation_started",
                status="started",
                level="info",
                message="Начинаю генерацию промпта через текстовый клиент",
            )

            prompt = await self._text_client.generate("prompt_for_kandinsky")

            if prompt:
                self.log_event(
                    event="prompt_generation_success",
                    status="success",
                    level="info",
                    message=f"Промпт успешно сгенерирован: {prompt[:100]}...",
                )
                return prompt

            self.log_event(
                event="prompt_generation_empty",
                status="empty",
                level="warning",
                message="Текстовый клиент вернул пустой промпт",
            )
            return None

        except Exception as e:
            self.logger.error(f"Ошибка при генерации промпта: {e}", exc_info=True)
            self.log_event(
                event="prompt_generation_failed",
                status="error",
                level="warning",
                message=f"Ошибка при генерации промпта: {e}",
            )
            # Не пробрасываем исключение, чтобы вызывающий код мог использовать fallback
            return None

    def get_fallback_prompt(self) -> str:
        """Возвращает статический промпт из конфигурации (fallback).

        Используется когда не удалось получить промпт через текстовый клиент.
        Выбирает случайный промпт и стиль из переданной конфигурации.

        Returns:
            Статический промпт для генерации изображения.
        """
        if not self._fallback_config or not self._fallback_config.frog_prompts or not self._fallback_config.styles:
            # Fallback на дефолтный промпт, если конфигурация не предоставлена
            return "cartoon frog, green, high quality, detailed, Wednesday frog meme"

        frog_prompt = random.choice(self._fallback_config.frog_prompts)
        style = random.choice(self._fallback_config.styles)
        return f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"
