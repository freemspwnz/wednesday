"""Протоколы для зависимостей сервисов."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from utils.images_repo import ImageRecord
    from utils.prompts_repo import PromptRecord


@runtime_checkable
class IMetrics(Protocol):
    """Протокол для системы метрик."""

    async def increment_generation_success(self) -> None:
        """Увеличивает счётчик успешных генераций изображений."""
        ...

    async def increment_generation_failed(self) -> None:
        """Увеличивает счётчик неудачных генераций изображений."""
        ...

    async def increment_cache_hit(self) -> None:
        """Увеличивает счётчик попаданий в кэш."""
        ...

    async def increment_dispatch_success(self) -> None:
        """Увеличивает счётчик успешных отправок сообщений."""
        ...

    async def increment_dispatch_failed(self) -> None:
        """Увеличивает счётчик неудачных отправок сообщений."""
        ...

    async def record_circuit_breaker_trip(self) -> None:
        """Увеличивает счётчик срабатываний circuit breaker."""
        ...


@runtime_checkable
class ICircuitBreaker(Protocol):
    """Протокол для circuit breaker."""

    async def is_open(self) -> bool:
        """Возвращает True, если circuit breaker открыт и запросы должны блокироваться."""
        ...

    async def record_success(self) -> None:
        """Регистрирует успешный запрос и, при необходимости, сбрасывает счётчик ошибок."""
        ...

    async def record_failure(self) -> None:
        """Регистрирует неудачу и обновляет состояние circuit breaker."""
        ...


@runtime_checkable
class IRateLimiter(Protocol):
    """Протокол для сервиса rate limiting."""

    async def is_allowed(self, key: str) -> bool:
        """Возвращает True, если запрос разрешён и инкрементирует счётчик по ключу."""
        ...

    async def reset(self, key: str) -> None:
        """Сбрасывает счётчик по ключу."""
        ...


@runtime_checkable
class IImageStorage(Protocol):
    """Протокол для файлового хранилища изображений."""

    async def save(self, data: bytes, folder: str | None = None, prefix: str = "frog") -> str:
        """Сохраняет байтовые данные изображения в файловое хранилище.

        Args:
            data: Данные для сохранения (байты).
            folder: Папка для сохранения.
            prefix: Префикс имени файла.

        Returns:
            Путь к сохранённому файлу.
        """
        ...

    async def get_random(self, folder: str | None = None) -> tuple[bytes, str] | None:
        """Получает случайный файл изображения из папки.

        Args:
            folder: Папка для поиска файла.

        Returns:
            Кортеж (данные файла, путь к файлу) или None, если файлы не найдены.
        """
        ...


T = TypeVar("T")


@runtime_checkable
class ICache(Protocol[T]):
    """Протокол для кэширования данных."""

    async def get(self, key: str) -> T | None:
        """Получает значение из кэша по ключу.

        Args:
            key: Ключ для получения значения.

        Returns:
            Значение из кэша или None, если ключ не найден.
        """
        ...

    async def set(self, key: str, value: T, ttl: int | None = None) -> None:
        """Сохраняет значение в кэш.

        Args:
            key: Ключ для сохранения.
            value: Значение для сохранения.
            ttl: Время жизни записи в секундах (опционально).
        """
        ...

    async def delete(self, key: str) -> None:
        """Удаляет значение из кэша.

        Args:
            key: Ключ для удаления.
        """
        ...


@runtime_checkable
class ITaskQueue(Protocol):
    """Протокол для отправки задач в очередь выполнения.

    Абстрагирует детали реализации очереди задач (Celery, Redis Streams, и т.д.)
    от application-сервисов.
    """

    async def send_frog_manual_task(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
    ) -> None:
        """Ставит задачу генерации и отправки жабы в очередь.

        Args:
            chat_id: ID чата для отправки изображения.
            user_id: ID пользователя, запросившего генерацию.
            status_message_id: ID статусного сообщения для удаления после отправки (опционально).

        Raises:
            Exception: При ошибке постановки задачи в очередь.
        """
        ...


@runtime_checkable
class IImageRepo(Protocol):
    """Протокол для репозитория изображений в БД."""

    async def get_by_prompt_hash(self, prompt_hash: str) -> ImageRecord | None:
        """Получает изображение по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            ImageRecord если изображение найдено, None иначе.
        """
        ...

    def load_image_bytes(self, image_record: ImageRecord) -> bytes:
        """Загружает байты изображения из файла по ImageRecord.

        Args:
            image_record: Запись ImageRecord с метаданными изображения.

        Returns:
            Байты изображения из файла.

        Raises:
            FileNotFoundError: Если файл изображения не найден на диске.
            OSError: При ошибке чтения файла.
        """
        ...

    async def get_or_create_image(
        self,
        prompt_hash: str,
        image_bytes: bytes,
    ) -> ImageRecord:
        """Создает или получает существующее изображение.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.
            image_bytes: Байты изображения для сохранения.

        Returns:
            ImageRecord с метаданными изображения (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных или файловой системе.
        """
        ...


@runtime_checkable
class IPromptRepo(Protocol):
    """Протокол для репозитория промптов в БД."""

    async def get_or_create_prompt(self, prompt_text: str) -> PromptRecord:
        """Создает или получает существующий промпт.

        Args:
            prompt_text: Исходный текст промпта.

        Returns:
            PromptRecord с метаданными промпта (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        ...

    async def get_prompt_by_hash(self, prompt_hash: str) -> PromptRecord | None:
        """Получает промпт по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            PromptRecord если промпт найден, None иначе.
        """
        ...
