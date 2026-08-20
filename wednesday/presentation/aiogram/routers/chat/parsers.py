"""Argument parsers for in-chat commands."""

_WEEKDAY_BY_KEY: dict[str, int] = {
    "mon": 1,
    "monday": 1,
    "понедельник": 1,
    "пн": 1,
    "tue": 2,
    "tuesday": 2,
    "вторник": 2,
    "вт": 2,
    "wed": 3,
    "wednesday": 3,
    "среда": 3,
    "ср": 3,
    "thu": 4,
    "thursday": 4,
    "четверг": 4,
    "чт": 4,
    "fri": 5,
    "friday": 5,
    "пятница": 5,
    "пт": 5,
    "sat": 6,
    "saturday": 6,
    "суббота": 6,
    "сб": 6,
    "sun": 7,
    "sunday": 7,
    "воскресенье": 7,
    "вс": 7,
}


def parse_schedule_time(raw: str) -> tuple[int, int]:
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
    return hour, minute


def parse_weekday(raw: str) -> int:
    key = raw.strip().lower()
    weekday = _WEEKDAY_BY_KEY.get(key)
    if weekday is None:
        msg = "Укажите день недели (mon…sun или пн…вс)"
        raise ValueError(msg)
    return weekday


def parse_timezone(raw: str) -> str:
    name = raw.strip()
    msg = "Укажите таймзону IANA, например Europe/Moscow"
    if not name:
        raise ValueError(msg)
    return name
