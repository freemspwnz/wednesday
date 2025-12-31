"""Протоколы для работы с мессенджерами."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IMessagingService(Protocol):
    """Протокол для сервиса отправки сообщений через мессенджеры.

    Абстрагирует детали реализации мессенджера (Telegram, и т.д.)
    от application-сервисов.
    """

    async def send_image(
        self,
        chat_id: str | int,
        image: bytes,
        caption: str,
    ) -> None:
        """Отправляет фото в указанный чат.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            image: Байты изображения.
            caption: Подпись к изображению.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        ...

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
    ) -> None:
        """Отправляет текстовое сообщение в указанный чат.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            text: Текст сообщения.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        ...

    async def delete_message(
        self,
        chat_id: str | int,
        message_id: str | int,
    ) -> None:
        """Удаляет сообщение из чата.

        Args:
            chat_id: ID чата (может быть str или int).
            message_id: ID сообщения для удаления (может быть str или int).

        Raises:
            MessagingNetworkError: При сетевых ошибках.
            MessagingAPIError: При ошибках API (сообщение не найдено, нет прав).
        """
        ...

    async def get_chat_details(
        self,
        chat_id: str | int,
        timeout: float = 10.0,
    ) -> dict[str, str | int | None] | None:
        """Получает детальную информацию о чате/пользователе.

        Args:
            chat_id: ID чата/пользователя для получения информации (может быть str или int).
            timeout: Таймаут для запроса в секундах.

        Returns:
            Словарь с информацией о чате/пользователе или None в случае ошибки.
            Ключи словаря: 'id', 'title', 'first_name', 'last_name', 'username', 'type'.
            Для чатов: 'title' заполнен, 'first_name'/'last_name' могут быть None.
            Для пользователей: 'first_name'/'last_name' заполнены, 'title' может быть None.

        Note:
            Универсальный метод, возвращающий структурированные данные вместо
            специфичного объекта мессенджера. Для graceful degradation возвращает None при ошибках.
        """
        ...

    async def send_file(
        self,
        chat_id: str | int,
        file: bytes,
        filename: str,
    ) -> None:
        """Отправляет файл в указанный чат.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            file: Байты файла.
            filename: Имя файла.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        ...

    async def send_reply(
        self,
        chat_id: str | int,
        text: str,
        reply_to_message_id: str | int | None = None,
    ) -> str | int:
        """Отправляет ответ на сообщение.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            text: Текст сообщения.
            reply_to_message_id: ID сообщения для ответа (опционально, может быть str или int).
                В разных мессенджерах механизм ответа может отличаться:
                - Telegram: использует message_id напрямую
                - WhatsApp: может требовать дополнительный контекст (thread_id)
                - VK: может требовать дополнительные параметры

        Returns:
            ID отправленного сообщения (может быть str или int).

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
            MessagingFeatureNotSupported: Если мессенджер не поддерживает reply или требуется
                дополнительный контекст, который не может быть передан через reply_to_message_id.
        """
        ...

    async def edit_message(
        self,
        chat_id: str | int,
        message_id: str | int,
        text: str,
    ) -> None:
        """Редактирует существующее сообщение.

        Args:
            chat_id: ID чата (может быть str или int).
            message_id: ID сообщения для редактирования (может быть str или int).
            text: Новый текст сообщения.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (сообщение не найдено, нет прав).
            MessagingFeatureNotSupported: Если мессенджер не поддерживает редактирование сообщений
                (например, WhatsApp не поддерживает редактирование).
        """
        ...


@runtime_checkable
class IFallbackImageProvider(Protocol):
    """Протокол для получения fallback изображений.

    Используется для получения случайных сохраненных изображений,
    которые отправляются при ошибках генерации.
    """

    async def get_random_saved_image(self) -> tuple[bytes, str] | None:
        """Возвращает случайное сохраненное изображение для fallback.

        Returns:
            Кортеж (байты изображения, подпись) или None, если изображение недоступно.
        """
        ...
