"""Вспомогательные функции для обработки рассылок по целевым чатам.

Выделены в отдельный модуль для переиспользования логики обработки целевых чатов
в `DispatchDeliveryService`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.dispatch_service import DispatchResult
from shared.protocols import IDispatchRegistry, ILogger


async def process_targets_with_registry_check(  # noqa: PLR0913
    *,
    dispatch_registry: IDispatchRegistry,
    logger: ILogger,
    slot_date: str,
    slot_time: str,
    targets: set[int],
    result: DispatchResult,
    per_target_sender: Callable[[int, DispatchResult], Awaitable[None]],
    skip_log_event: str = "dispatch_already_sent",
) -> None:
    """Общий helper для обхода таргетов с проверкой реестра отправок.

    Args:
        dispatch_registry: Реестр отправок для проверки уже обработанных слотов.
        logger: Логгер для вывода диагностических сообщений.
        slot_date: Дата слота в формате YYYY-MM-DD.
        slot_time: Время слота в формате HH:MM.
        targets: Множество ID целевых чатов.
        result: Результат рассылки для обновления (передаётся в per_target_sender).
        per_target_sender: Коллбек, выполняющий всю работу по отправке для одного чата.
        skip_log_event: Имя события для логирования пропущенных отправок.
    """
    for target_chat in targets:
        # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
        if await dispatch_registry.is_dispatched(
            slot_date,
            slot_time,
            target_chat,
        ):
            logger.info(
                (f"Пропускаем отправку в чат {target_chat} - уже отправлено в слот {slot_date}_{slot_time}"),
                event=skip_log_event,
                chat_id=target_chat,
                slot_date=slot_date,
                slot_time=slot_time,
            )
            continue

        await per_target_sender(target_chat, result)
