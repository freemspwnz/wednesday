"""Протоколы для работы с очередями задач."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


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
class IIdempotencyService(Protocol):
    """Протокол для сервиса идемпотентности операций.

    Обеспечивает выполнение операций с проверкой идемпотентности через кэширование результатов.
    Используется для предотвращения дублирования выполнения задач в Celery.
    """

    async def execute_with_idempotency(
        self,
        key: str,
        ttl: int,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Выполняет операцию с проверкой идемпотентности.

        Если операция с данным ключом уже выполнялась и результат кэширован,
        возвращает кэшированный результат. Иначе выполняет операцию и кэширует результат.

        Args:
            key: Уникальный ключ идемпотентности для операции.
            ttl: Время жизни кэшированного результата в секундах.
            operation: Асинхронная операция для выполнения (callable без аргументов).

        Returns:
            Результат выполнения операции (из кэша или новый).

        Raises:
            ValueError: Если формат кэшированного результата невалиден.
            Exception: При ошибке выполнения операции или работы с кэшем.
        """
        ...
