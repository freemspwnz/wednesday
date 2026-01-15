"""Утилиты для работы с асинхронным кодом.

Содержит общие утилиты для работы с asyncio, не специфичные для конкретного слоя.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.protocols.infrastructure import ILogger


async def gather_with_timeout(
    *tasks: Awaitable,
    timeout: float | None = None,
    return_exceptions: bool = True,
    default_timeout: float = 5.0,
    logger: ILogger | None = None,
) -> list:
    """Выполняет asyncio.gather с таймаутом для всех задач.

    Оборачивает каждую задачу в asyncio.wait_for для защиты от зависаний.
    Если таймаут не указан, используется значение по умолчанию.

    Args:
        *tasks: Асинхронные задачи для параллельного выполнения.
        timeout: Таймаут для каждой задачи в секундах. Если None, используется
            default_timeout.
        return_exceptions: Если True, исключения возвращаются как результаты,
            а не пробрасываются.
        default_timeout: Таймаут по умолчанию в секундах.
        logger: Логгер для логирования предупреждений (опционально).

    Returns:
        Список результатов выполнения задач. Если return_exceptions=True,
        исключения включаются в список как элементы.

    Side Effects:
        - Логирует предупреждения при таймаутах (если logger передан).
        - Защищает от зависания при проблемах с сетью.
    """
    if timeout is None:
        timeout = default_timeout

    async def _with_timeout(task: Awaitable) -> object:
        """Оборачивает задачу в таймаут."""
        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except TimeoutError as e:
            if logger:
                logger.warning(f"Таймаут {timeout}с при выполнении задачи")
            if return_exceptions:
                return e
            raise

    wrapped_tasks = [_with_timeout(task) for task in tasks]
    return await asyncio.gather(*wrapped_tasks, return_exceptions=return_exceptions)
