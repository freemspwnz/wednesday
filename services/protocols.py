"""Протоколы для зависимостей сервисов."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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
class IStorage(Protocol):
    """Протокол для файлового хранилища."""

    async def save(self, data: bytes, folder: str, prefix: str) -> str:
        """Сохраняет данные в файловое хранилище.

        Args:
            data: Данные для сохранения (байты).
            folder: Папка для сохранения.
            prefix: Префикс имени файла.

        Returns:
            Путь к сохранённому файлу.
        """
        ...

    async def get_random(self, folder: str) -> tuple[bytes, str] | None:
        """Получает случайный файл из папки.

        Args:
            folder: Папка для поиска файла.

        Returns:
            Кортеж (данные файла, путь к файлу) или None, если файлы не найдены.
        """
        ...


@runtime_checkable
class ICache(Protocol):
    """Протокол для кэширования данных."""

    async def get(self, key: str) -> object | None:
        """Получает значение из кэша по ключу.

        Args:
            key: Ключ для получения значения.

        Returns:
            Значение из кэша или None, если ключ не найден.
        """
        ...

    async def set(self, key: str, value: object, ttl: int | None = None) -> None:
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
