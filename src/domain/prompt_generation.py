"""Доменный сервис для генерации промптов.

Содержит чистую логику генерации промптов без зависимостей от инфраструктуры
(кэш, файловое хранилище, база данных).
"""

from __future__ import annotations

import random

from shared.base.base_service import BaseService
from shared.base.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    NetworkError,
)
from shared.config import PromptFallbackConfig
from shared.protocols import ILogger, ITextToTextClient


class PromptGenerationService(BaseService):
    """Доменный сервис для генерации промптов.

    Выполняет чистую генерацию промптов через ITextToTextClient с fallback
    на статический промпт. Не зависит от инфраструктуры (кэш, файлы, БД).
    """

    def __init__(
        self,
        text_client: ITextToTextClient | None = None,
        fallback_config: PromptFallbackConfig | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис генерации промптов.

        Args:
            text_client: Клиент для генерации текста (опционально). Если None,
                используется только статический fallback.
            fallback_config: Конфигурация для fallback промптов (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._text_client = text_client
        self._fallback_config = fallback_config

    async def generate(self) -> str | None:
        """Генерирует промпт для генерации изображения.

        Выполняет генерацию через ITextToTextClient. При ошибке возвращает None,
        что сигнализирует о необходимости использовать статический fallback
        в вызывающем коде.

        Returns:
            Сгенерированный промпт или None, если генерация не удалась.

        Note:
            Метод не пробрасывает исключения клиента, а возвращает None,
            чтобы вызывающий код мог использовать fallback промпт.
        """
        if self._text_client is None:
            self.logger.info(
                "Текстовый клиент не настроен, используем статический fallback",
                event="prompt_generation_skipped",
                status="no_client",
            )
            return None

        try:
            self.logger.info(
                "Начинаю генерацию промпта через текстовый клиент",
                event="prompt_generation_started",
                status="started",
            )

            prompt = await self._text_client.generate("prompt_for_kandinsky")

            self.logger.info(
                f"Промпт успешно сгенерирован: {prompt[:100]}...",
                event="prompt_generation_success",
                status="success",
            )
            return prompt

        except AuthenticationError as exc:
            self.logger.warning(
                f"Ошибка аутентификации при генерации промпта: {exc}",
                event="prompt_generation_failed",
                status="auth_error",
            )
            # Не пробрасываем исключение, чтобы вызывающий код мог использовать fallback
            return None
        except NetworkError as exc:
            self.logger.warning(
                f"Сетевая ошибка при генерации промпта: {exc}",
                event="prompt_generation_failed",
                status="network_error",
            )
            # Не пробрасываем исключение, чтобы вызывающий код мог использовать fallback
            return None
        except APIError as exc:
            self.logger.warning(
                f"Ошибка API при генерации промпта: {exc}",
                event="prompt_generation_failed",
                status="api_error",
            )
            # Не пробрасываем исключение, чтобы вызывающий код мог использовать fallback
            return None
        except ClientError as exc:
            self.logger.warning(
                f"Ошибка клиента при генерации промпта: {exc}",
                event="prompt_generation_failed",
                status="client_error",
            )
            # Не пробрасываем исключение, чтобы вызывающий код мог использовать fallback
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при генерации промпта: {e}", exc_info=True)
            self.logger.warning(
                f"Ошибка при генерации промпта: {e}",
                event="prompt_generation_failed",
                status="error",
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
