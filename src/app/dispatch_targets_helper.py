"""Вспомогательные функции для обработки рассылок по целевым чатам.

Выделены в отдельный модуль для переиспользования логики обработки целевых чатов
в `DispatchDeliveryService`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shared.protocols import IDispatchRegistry, ILogger


async def check_dispatch_status_batch(
    dispatch_registry: IDispatchRegistry,
    slot_date: str,
    slot_time: str,
    chat_ids: set[int],
) -> dict[int, bool]:
    """Проверяет статус отправки для множества чатов (batch).

    Унифицированная функция для проверки статуса отправки для нескольких чатов
    за один запрос к БД. Используется для оптимизации вместо N отдельных запросов.

    Args:
        dispatch_registry: Реестр отправок.
        slot_date: Дата слота в формате YYYY-MM-DD.
        slot_time: Время слота в формате HH:MM.
        chat_ids: Множество ID чатов для проверки.

    Returns:
        Словарь {chat_id: bool} - True если отправлено, False иначе.
    """
    return await dispatch_registry.are_dispatched_batch(
        slot_date=slot_date,
        slot_time=slot_time,
        chat_ids=chat_ids,
    )


def are_all_dispatched(status_map: dict[int, bool]) -> bool:
    """Проверяет, отправлено ли во все чаты.

    Args:
        status_map: Словарь {chat_id: bool} из check_dispatch_status_batch.

    Returns:
        True если все чаты отправлены, False иначе.
        Если status_map пуст, возвращает True (нет чатов для проверки).
    """
    if not status_map:
        return True
    return all(status_map.values())


def get_undispatched_chats(
    targets: set[int],
    status_map: dict[int, bool],
) -> set[int]:
    """Возвращает множество чатов, которые еще не отправлены.

    Args:
        targets: Множество всех целевых чатов.
        status_map: Словарь {chat_id: bool} из check_dispatch_status_batch.

    Returns:
        Множество ID чатов, которые еще не отправлены.
    """
    return {chat_id for chat_id in targets if not status_map.get(chat_id, False)}


@dataclass
class DispatchResult:
    """Типизированный контейнер результата отправки.

    Использует dataclass для явной мутации полей (frozen=False по умолчанию).
    Это более безопасно, чем TypedDict, так как обеспечивает валидацию типов
    и предотвращает добавление несуществующих полей.
    Стандарт: Dataclass для мутабельных DTO, TypedDict для неизменяемых структур.

    Attributes:
        slot_date: Дата слота в формате YYYY-MM-DD.
        slot_time: Время слота в формате HH:MM.
        total_targets: Всего целевых чатов.
        success_count: Количество успешных отправок.
        failed_count: Количество неуспешных отправок (по Telegram/программным ошибкам).
        used_fallback: Использован ли fallback‑сценарий вместо свежей генерации.
    """

    slot_date: str
    slot_time: str
    total_targets: int
    success_count: int
    failed_count: int
    used_fallback: bool


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

    Использует batch-проверку для оптимизации (один запрос вместо N).

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
    if not targets:
        return

    # Batch-проверка всех чатов за один запрос
    status_map = await check_dispatch_status_batch(
        dispatch_registry=dispatch_registry,
        slot_date=slot_date,
        slot_time=slot_time,
        chat_ids=targets,
    )

    # Обрабатываем только неотправленные чаты
    for target_chat in targets:
        if status_map.get(target_chat, False):
            logger.info(
                (f"Пропускаем отправку в чат {target_chat} - уже отправлено в слот {slot_date}_{slot_time}"),
                event=skip_log_event,
                chat_id=target_chat,
                slot_date=slot_date,
                slot_time=slot_time,
            )
            continue

        await per_target_sender(target_chat, result)
