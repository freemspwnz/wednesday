"""Inline keyboards for schedule menu (main + submenu stubs)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.dto import ChatContext

from ....messages import chat as chat_msg
from .data import ScheduleData

_WEEKDAY_SHORT: dict[int, str] = {
    1: "пн",
    2: "вт",
    3: "ср",
    4: "чт",
    5: "пт",
    6: "сб",
    7: "вс",
}

TIMEZONE_PRESETS: tuple[str, ...] = (
    "UTC",
    "Europe/Moscow",
    "Europe/Kyiv",
    "Asia/Yekaterinburg",
    "Asia/Vladivostok",
)


def build_main_kb(chat: ChatContext) -> InlineKeyboardMarkup:
    """Root schedule menu: current values as button labels."""
    status = "активна" if chat.is_active else "приостановлена"
    day = chat_msg.weekday_label(chat.weekday)
    slots = _slots_label(chat.schedules)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(f"Рассылка: {status}", action="open", value="status")],
            [_btn(f"День: {day}", action="open", value="day")],
            [_btn(f"TZ: {chat.timezone}", action="open", value="tz")],
            [_btn(f"Слоты: {slots}", action="open", value="slots")],
        ],
    )


def build_status_kb(*, is_active: bool) -> InlineKeyboardMarkup:
    """Stub: enable / disable + back."""
    rows: list[list[InlineKeyboardButton]] = []
    if is_active:
        rows.append([_btn("Выключить", action="stub", value="deactivate")])
    else:
        rows.append([_btn("Включить", action="stub", value="activate")])
    rows.append([_back_btn()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_day_kb(*, current: int) -> InlineKeyboardMarkup:
    """Stub: weekday picker + back."""
    row: list[InlineKeyboardButton] = []
    for day in range(1, 8):
        mark = "·" if day == current else ""
        label = f"{mark}{_WEEKDAY_SHORT[day]}{mark}"
        row.append(_btn(label, action="stub", value=f"d{day}"))
    return InlineKeyboardMarkup(inline_keyboard=[row, [_back_btn()]])


def build_tz_kb(*, current: str) -> InlineKeyboardMarkup:
    """Stub: timezone presets + back."""
    rows: list[list[InlineKeyboardButton]] = []
    for index, tz in enumerate(TIMEZONE_PRESETS):
        mark = "✓ " if tz == current else ""
        rows.append([_btn(f"{mark}{tz}", action="stub", value=f"tz{index}")])
    rows.append([_back_btn()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_slots_kb() -> InlineKeyboardMarkup:
    """Stub: add / remove / clear + back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Добавить", action="stub", value="add"),
                _btn("Удалить", action="stub", value="remove"),
            ],
            [_btn("Очистить", action="stub", value="clear")],
            [_back_btn()],
        ],
    )


_SLOTS_LABEL_MAX = 28


def _slots_label(schedules: list[tuple[int, int]]) -> str:
    if not schedules:
        return "нет"
    ordered = sorted(schedules, key=lambda s: (s[0], s[1]))
    text = ", ".join(f"{h:02d}:{m:02d}" for h, m in ordered)
    if len(text) > _SLOTS_LABEL_MAX:
        return f"{text[: _SLOTS_LABEL_MAX - 3]}…"
    return text


def _btn(text: str, *, action: str, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=ScheduleData(action=action, value=value).pack(),
    )


def _back_btn() -> InlineKeyboardButton:
    return _btn(chat_msg.SCHEDULE_BACK, action="menu")
