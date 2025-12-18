"""Протоколы для зависимостей сервисов."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo


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
class IScheduler(Protocol):
    """Протокол для абстракции планировщика задач."""

    send_times: list[str]
    wednesday: int
    tz: ZoneInfo

    def schedule_wednesday_task(self, task_func: Callable[[str | None], Awaitable[None]]) -> None:
        """Планирует задачу на выполнение каждую среду."""
        ...

    def schedule_daily_task(self, task_func: Callable[[], Awaitable[None]], time_str: str) -> None:
        """Планирует задачу на выполнение каждый день в указанное время."""
        ...

    def schedule_interval_task(self, task_func: Callable[[], Awaitable[None]], interval_minutes: int) -> None:
        """Планирует задачу на выполнение с заданным интервалом."""
        ...

    async def start(self) -> None:
        """Запускает цикл планировщика задач."""
        ...

    def stop(self) -> None:
        """Останавливает планировщик задач."""
        ...

    def get_next_run(self) -> datetime | None:
        """Возвращает время следующего запланированного выполнения."""
        ...

    def clear_all_jobs(self) -> None:
        """Очищает все запланированные задачи."""
        ...

    def get_jobs_count(self) -> int:
        """Возвращает количество запланированных задач."""
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


@runtime_checkable
class IPromptStorage(Protocol):
    """Протокол для файлового хранилища промптов."""

    async def save(
        self,
        prompt: str,
        folder: Path | str | None = None,
        source: str = "gigachat",
    ) -> str:
        """Сохраняет промпт в файловое хранилище и возвращает путь к файлу."""
        ...

    async def load_all(self, folder: Path | str | None = None) -> list[str]:
        """Загружает все сохранённые промпты из указанной папки."""
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
