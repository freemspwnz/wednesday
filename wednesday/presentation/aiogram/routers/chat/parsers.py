"""Argument parsers for in-chat commands."""

from zoneinfo import ZoneInfo

from domain.chat import ChatSchedule, Weekday

_WEEKDAY_BY_KEY: dict[str, Weekday] = {
    "mon": Weekday.MONDAY,
    "monday": Weekday.MONDAY,
    "понедельник": Weekday.MONDAY,
    "пн": Weekday.MONDAY,
    "tue": Weekday.TUESDAY,
    "tuesday": Weekday.TUESDAY,
    "вторник": Weekday.TUESDAY,
    "вт": Weekday.TUESDAY,
    "wed": Weekday.WEDNESDAY,
    "wednesday": Weekday.WEDNESDAY,
    "среда": Weekday.WEDNESDAY,
    "ср": Weekday.WEDNESDAY,
    "thu": Weekday.THURSDAY,
    "thursday": Weekday.THURSDAY,
    "четверг": Weekday.THURSDAY,
    "чт": Weekday.THURSDAY,
    "fri": Weekday.FRIDAY,
    "friday": Weekday.FRIDAY,
    "пятница": Weekday.FRIDAY,
    "пт": Weekday.FRIDAY,
    "sat": Weekday.SATURDAY,
    "saturday": Weekday.SATURDAY,
    "суббота": Weekday.SATURDAY,
    "сб": Weekday.SATURDAY,
    "sun": Weekday.SUNDAY,
    "sunday": Weekday.SUNDAY,
    "воскресенье": Weekday.SUNDAY,
    "вс": Weekday.SUNDAY,
}


def parse_schedule_time(raw: str) -> ChatSchedule:
    text = raw.strip()
    if ":" not in text:
        msg = "Укажите время в формате ЧЧ:ММ"
        raise ValueError(msg)
    hour_raw, minute_raw = text.split(":", maxsplit=1)
    try:
        hour = int(hour_raw)
        minute = int(minute_raw)
    except ValueError as exc:
        msg = "Укажите время в формате ЧЧ:ММ"
        raise ValueError(msg) from exc
    return ChatSchedule(hour=hour, minute=minute)


def parse_weekday(raw: str) -> Weekday:
    key = raw.strip().lower()
    weekday = _WEEKDAY_BY_KEY.get(key)
    if weekday is None:
        msg = "Укажите день недели (mon…sun или понедельник…воскресенье)"
        raise ValueError(msg)
    return weekday


def parse_timezone(raw: str) -> ZoneInfo:
    name = raw.strip()
    if not name:
        msg = "Укажите таймзону IANA, например Europe/Moscow"
        raise ValueError(msg)
    try:
        return ZoneInfo(name)
    except Exception as exc:
        msg = "Укажите корректную таймзону IANA, например Europe/Moscow"
        raise ValueError(msg) from exc
