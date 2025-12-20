"""Результат выполнения рассылки Wednesday Frog."""

from __future__ import annotations


class DispatchResult(dict):
    """Простейший контейнер результата отправки.

    Ключи:
        - slot_date: дата слота (YYYY-MM-DD)
        - slot_time: время слота (HH:MM)
        - total_targets: всего целевых чатов
        - success_count: количество успешных отправок
        - failed_count: количество неуспешных отправок (по Telegram/программным ошибкам)
        - used_fallback: использован ли fallback‑сценарий вместо свежей генерации
    """
