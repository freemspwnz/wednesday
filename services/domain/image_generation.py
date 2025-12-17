"""Доменный сервис для генерации изображений.

Содержит чистую логику генерации изображений без зависимостей от инфраструктуры
(кэш, метрики, circuit breaker, файловое хранилище).
"""

from __future__ import annotations

from services.base.base_service import BaseService
from services.base.exceptions import ImageGenerationError
from services.clients import ITextToImageClient


class ImageGenerationService(BaseService):
    """Доменный сервис для генерации изображений.

    Выполняет чистую генерацию изображений через ITextToImageClient без
    зависимостей от инфраструктуры (кэш, метрики, circuit breaker).
    """

    def __init__(self, image_client: ITextToImageClient) -> None:
        """Инициализирует сервис генерации изображений.

        Args:
            image_client: Клиент для генерации изображений по текстовому промпту.
        """
        super().__init__()
        self._image_client = image_client

    async def generate(
        self,
        prompt: str,
        user_id: int | None = None,
    ) -> bytes | None:
        """Генерирует изображение по промпту.

        Выполняет чистую генерацию через ITextToImageClient без кэширования,
        метрик и других инфраструктурных зависимостей.

        Args:
            prompt: Текстовый промпт для генерации изображения.
            user_id: Идентификатор пользователя для логирования (опционально).

        Returns:
            Байты изображения или None при ошибке.

        Raises:
            ImageGenerationError: При критических ошибках генерации.
        """
        try:
            user_id_str = str(user_id) if user_id is not None else None
            self.log_event(
                event="image_generation_started",
                user_id=user_id_str,
                status="started",
                level="info",
                message=f"Начинаю генерацию изображения для промпта: {prompt[:100]}...",
            )

            image_data = await self._image_client.generate(prompt, user_id=user_id_str)

            if image_data:
                self.log_event(
                    event="image_generation_success",
                    user_id=user_id_str,
                    status="success",
                    level="info",
                    message="Изображение успешно сгенерировано",
                )
                return image_data

            self.log_event(
                event="image_generation_failed",
                user_id=user_id_str,
                status="error",
                level="warning",
                message="Клиент вернул None при генерации изображения",
            )
            return None

        except Exception as e:
            self.logger.error(f"Ошибка при генерации изображения: {e}", exc_info=True)
            raise ImageGenerationError(f"Ошибка при генерации изображения: {e}") from e
