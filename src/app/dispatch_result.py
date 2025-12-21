"""Результат выполнения рассылки Wednesday Frog."""

from __future__ import annotations

from typing import TypedDict


class DispatchResult(TypedDict):
    """Типизированный контейнер результата отправки.

    Ключи:
        - slot_date: дата слота (YYYY-MM-DD)
        - slot_time: время слота (HH:MM)
        - total_targets: всего целевых чатов
        - success_count: количество успешных отправок
        - failed_count: количество неуспешных отправок (по Telegram/программным ошибкам)
        - used_fallback: использован ли fallback‑сценарий вместо свежей генерации
    """

    slot_date: str
    slot_time: str
    total_targets: int
    success_count: int
    failed_count: int
    used_fallback: bool
