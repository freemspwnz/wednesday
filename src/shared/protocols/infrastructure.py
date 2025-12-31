"""Инфраструктурные протоколы: метрики, circuit breaker, rate limiter, storage, cache, logger."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    import asyncpg
else:
    import asyncpg

T = TypeVar("T")


@runtime_checkable
class IMetrics(Protocol):
    """Протокол для системы метрик."""

    async def increment_generation_success(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик успешных генераций изображений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).
        """
        ...

    async def increment_generation_failed(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик неудачных генераций изображений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).
        """
        ...

    async def increment_cache_hit(self) -> None:
        """Увеличивает счётчик попаданий в кэш."""
        ...

    async def increment_dispatch_success(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик успешных отправок сообщений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).
        """
        ...

    async def increment_dispatch_failed(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик неудачных отправок сообщений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).
        """
        ...

    async def record_circuit_breaker_trip(self) -> None:
        """Увеличивает счётчик срабатываний circuit breaker."""
        ...

    async def increment_generation_success_with_pool(self) -> None:
        """Увеличивает счётчик успешных генераций, получая connection из pool.

        Helper-метод для использования вне UoW контекста.
        """
        ...

    async def increment_generation_failed_with_pool(self) -> None:
        """Увеличивает счётчик неудачных генераций, получая connection из pool.

        Helper-метод для использования вне UoW контекста.
        """
        ...

    async def increment_dispatch_failed_with_pool(self) -> None:
        """Увеличивает счётчик неудачных отправок, получая connection из pool.

        Helper-метод для использования вне UoW контекста.
        """
        ...

    async def get_summary(self) -> dict[str, Any]:
        """Возвращает сводку всех метрик производительности.

        Returns:
            Словарь с ключами:
            - generations_total: общее количество генераций
            - generations_success: количество успешных генераций
            - generations_failed: количество неудачных генераций
            - generations_retries: количество повторных попыток
            - average_generation_time: среднее время генерации в секундах (строка)
            - dispatches_success: количество успешных отправок
            - dispatches_failed: количество неудачных отправок
            - circuit_breaker_trips: количество срабатываний circuit breaker
        """
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

    async def get_by_path(self, path: str) -> bytes:
        """Загружает изображение по пути к файлу.

        Args:
            path: Путь к файлу в хранилище.

        Returns:
            Байты изображения.

        Raises:
            FileNotFoundError: Если файл не найден.
            StorageError: При ошибках чтения файла.
        """
        ...

    async def delete(self, path: str) -> None:
        """Удаляет файл из хранилища.

        Args:
            path: Путь к файлу для удаления.

        Raises:
            FileNotFoundError: Если файл не найден.
            OSError: При ошибках файловой системы.
        """
        ...


@runtime_checkable
class ICache(Protocol[T]):
    """Протокол для кэширования данных.

    Определяет минимальный интерфейс для кэширования данных с поддержкой TTL.
    Используется для кэширования промптов и других временных данных.

    Реализации:
        - PromptCache: кэширование промптов в Redis с fallback в память
    """

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
                Если None, реализация может использовать значение по умолчанию.
        """
        ...

    async def delete(self, key: str) -> None:
        """Удаляет значение из кэша.

        Args:
            key: Ключ для удаления.
        """
        ...


@runtime_checkable
class ILogger(Protocol):
    """Протокол для системы логирования.

    Чистый интерфейс без зависимостей от конкретной реализации логирования.
    """

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне TRACE.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне DEBUG.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне INFO.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне SUCCESS.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне WARNING.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне ERROR.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне CRITICAL.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def bind(self, **kwargs: Any) -> ILogger:  # noqa: ANN401
        """Создает новый экземпляр логгера с привязанным контекстом.

        Args:
            **kwargs: Контекстные данные для привязки ко всем последующим логам.

        Returns:
            Новый экземпляр ILogger с обновленным контекстом.
        """
        ...
