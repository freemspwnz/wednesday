"""Inline callback data for schedule keyboard navigation."""

from aiogram.filters.callback_data import CallbackData


class ScheduleData(CallbackData, prefix="sch"):
    """Short payload: action + optional value (stay under Telegram 64-byte limit)."""

    action: str
    value: str = ""
