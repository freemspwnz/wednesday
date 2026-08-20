"""Inline keyboards for schedule menu (main + submenus)."""

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
    "Europe/Kaliningrad",
    "Asia/Novosibirsk",
    "Asia/Vladivostok",
)

MINUTE_STEPS: tuple[int, ...] = (0, 15, 30, 45)
_HOURS_PER_ROW = 6
_SLOTS_LABEL_MAX = 28
_HHMM_LEN = 4
_HOUR_MAX = 23
_MINUTE_MAX = 59


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
            [_btn("Закрыть", action="close")],
        ],
    )


def build_status_kb(*, is_active: bool) -> InlineKeyboardMarkup:
    """Enable / disable + back."""
    rows: list[list[InlineKeyboardButton]] = []
    if is_active:
        rows.append([_btn("Выключить", action="status", value="off")])
    else:
        rows.append([_btn("Включить", action="status", value="on")])
    rows.append([_back_main()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_day_kb(*, current: int) -> InlineKeyboardMarkup:
    """Weekday picker + back."""
    row: list[InlineKeyboardButton] = []
    for day in range(1, 8):
        mark = "·" if day == current else ""
        label = f"{mark}{_WEEKDAY_SHORT[day]}{mark}"
        row.append(_btn(label, action="day", value=str(day)))
    return InlineKeyboardMarkup(inline_keyboard=[row, [_back_main()]])


def build_tz_kb(*, current: str) -> InlineKeyboardMarkup:
    """Timezone presets + back."""
    rows: list[list[InlineKeyboardButton]] = []
    for index, tz in enumerate(TIMEZONE_PRESETS):
        mark = "✓ " if tz == current else ""
        rows.append([_btn(f"{mark}{tz}", action="tz", value=str(index))])
    rows.append([_back_main()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_slots_kb() -> InlineKeyboardMarkup:
    """Add / remove / clear + back to main."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Добавить", action="hours"),
                _btn("Удалить", action="rmlist"),
            ],
            [_btn("Очистить", action="clear", value="ask")],
            [_back_main()],
        ],
    )


def build_hours_kb() -> InlineKeyboardMarkup:
    """Hour grid (00–23) + back to slots."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for hour in range(24):
        row.append(_btn(f"{hour:02d}", action="mins", value=str(hour)))
        if len(row) == _HOURS_PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_back_slots()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_minutes_kb(*, hour: int) -> InlineKeyboardMarkup:
    """Minute steps for a chosen hour + back to hours."""
    row = [
        _btn(
            f"{hour:02d}:{minute:02d}",
            action="add",
            value=_pack_hhmm(hour, minute),
        )
        for minute in MINUTE_STEPS
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row, [_btn(chat_msg.SCHEDULE_BACK, action="hours")]])


def build_remove_kb(schedules: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    """Existing slots as remove targets + back to slots."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            _btn(
                f"{hour:02d}:{minute:02d}",
                action="rm",
                value=_pack_hhmm(hour, minute),
            )
        ]
        for hour, minute in sorted(schedules, key=lambda s: (s[0], s[1]))
    ]
    rows.append([_back_slots()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_clear_confirm_kb() -> InlineKeyboardMarkup:
    """Confirm clearing all slots."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Да, очистить", action="clear", value="yes"),
                _btn("Отмена", action="clear", value="no"),
            ],
        ],
    )


def pack_hhmm(hour: int, minute: int) -> str:
    return _pack_hhmm(hour, minute)


def unpack_hhmm(raw: str) -> tuple[int, int]:
    if len(raw) != _HHMM_LEN or not raw.isdigit():
        msg = "Некорректное время."
        raise ValueError(msg)
    hour = int(raw[:2])
    minute = int(raw[2:])
    if hour > _HOUR_MAX or minute > _MINUTE_MAX:
        msg = "Некорректное время."
        raise ValueError(msg)
    return hour, minute


def _pack_hhmm(hour: int, minute: int) -> str:
    return f"{hour:02d}{minute:02d}"


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


def _back_main() -> InlineKeyboardButton:
    return _btn(chat_msg.SCHEDULE_BACK, action="menu")


def _back_slots() -> InlineKeyboardButton:
    return _btn(chat_msg.SCHEDULE_BACK, action="open", value="slots")
