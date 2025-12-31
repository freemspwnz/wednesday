"""Протоколы для сервисов приложения."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from shared.models import FrogRequestResult


@runtime_checkable
class IImageService(Protocol):
    """Протокол для сервиса генерации изображений.

    Используется в Celery tasks для избежания зависимости от app-слоя.
    """

    async def generate_frog_image(
        self,
        user_id: int | None = None,
    ) -> tuple[bytes, str]:
        """Генерирует изображение жабы.

        Args:
            user_id: ID пользователя (опционально).

        Returns:
            Кортеж (байты изображения, подпись).

        Raises:
            ImageGenerationError: При ошибке генерации.
        """
        ...

    async def get_random_saved_image(self) -> tuple[bytes, str] | None:
        """Возвращает случайное сохранённое изображение.

        Returns:
            Кортеж (байты изображения, подпись) или None.
        """
        ...


@runtime_checkable
class IFrogProcessingService(Protocol):
    """Протокол для сервиса обработки запросов генерации жабы.

    Используется в Celery tasks для избежания зависимости от app-слоя.
    """

    async def process_frog_request(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None = None,
    ) -> FrogRequestResult:
        """Обрабатывает запрос на генерацию и отправку жабы.

        Args:
            chat_id: ID чата для отправки.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения для удаления (опционально).

        Returns:
            FrogRequestResult с результатом обработки.
        """
        ...
