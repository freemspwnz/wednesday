"""Chat messages: membership events and schedule commands."""

from zoneinfo import ZoneInfo

from app.dto import ChatContext
from domain.chat import Chat, ChatSchedule, Weekday

BOT_ADDED_TO_CHAT = "Привет! Я Wednesday Frog Bot!\n\nНажми /start и я расскажу, что я умею."

MEMBER_JOINED = [
    "Хей",
    "Здаров",
    "Че как?",
    "Че хотел?",
    "Че каво?",
    "Прив",
    "Привет",
    "Йоу",
]

MEMBER_LEFT = [
    "Уходи",
    "Да это жёстко",
    "Так ему и надо! (извините)",
    "Так его! (извините)",
    "Пшёл вон!",
]

SCHEDULE_USAGE = (
    "Команды расписания:\n"
    "/schedule — показать расписание\n"
    "/schedule_add ЧЧ:ММ — добавить время\n"
    "/schedule_remove ЧЧ:ММ — удалить время\n"
    "/schedule_clear — очистить все слоты\n"
    "/schedule_day <день> — день недели (wed, среда…)\n"
    "/schedule_tz <IANA> — таймзона (Europe/Moscow)"
)

SCHEDULE_ADD_USAGE = "Использование: /schedule_add ЧЧ:ММ"

SCHEDULE_REMOVE_USAGE = "Использование: /schedule_remove ЧЧ:ММ"

SCHEDULE_DAY_USAGE = "Использование: /schedule_day <день>"

SCHEDULE_TZ_USAGE = "Использование: /schedule_tz <таймзона>"


def weekday_label(weekday: Weekday) -> str:
    return _WEEKDAY_LABELS.get(weekday, str(weekday))


_WEEKDAY_LABELS: dict[Weekday, str] = {
    Weekday.MONDAY: "понедельник",
    Weekday.TUESDAY: "вторник",
    Weekday.WEDNESDAY: "среда",
    Weekday.THURSDAY: "четверг",
    Weekday.FRIDAY: "пятница",
    Weekday.SATURDAY: "суббота",
    Weekday.SUNDAY: "воскресенье",
}


def _format_time(slot: ChatSchedule) -> str:
    return f"{slot.hour:02d}:{slot.minute:02d}"


def format_schedule_context(chat: ChatContext) -> str:
    """Format current schedule from registration context."""
    return _format_schedule(
        is_active=chat.is_active,
        weekday=chat.weekday,
        timezone=chat.timezone,
        schedules=chat.schedules,
    )


def format_schedule_chat(chat: Chat) -> str:
    """Format schedule from chat aggregate returned by use case."""
    from domain.chat import ActiveState

    return _format_schedule(
        is_active=isinstance(chat.state, ActiveState),
        weekday=chat.schedules.weekday,
        timezone=chat.schedules.timezone,
        schedules=chat.schedules.schedules,
    )


def _format_schedule(
    *,
    is_active: bool,
    weekday: Weekday,
    timezone: ZoneInfo,
    schedules: tuple[ChatSchedule, ...],
) -> str:
    status = "активна" if is_active else "приостановлена"
    day = _WEEKDAY_LABELS.get(weekday, str(weekday))
    if schedules:
        slots = ", ".join(_format_time(slot) for slot in sorted(schedules, key=lambda s: (s.hour, s.minute)))
    else:
        slots = "нет слотов"
    return f"📅 Расписание чата\n\nРассылка: {status}\nДень: {day}\nТаймзона: {timezone}\nВремена: {slots}"
