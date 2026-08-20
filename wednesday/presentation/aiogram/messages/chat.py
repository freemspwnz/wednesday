"""Chat messages: membership events and schedule commands."""

from app.dto import ChatContext

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
    "Команды чата:\n"
    "/schedule — показать расписание\n"
    "/activate — включить рассылку\n"
    "/deactivate — приостановить рассылку\n"
    "/schedule_add ЧЧ:ММ — добавить время\n"
    "/schedule_remove ЧЧ:ММ — удалить время\n"
    "/schedule_clear — очистить все слоты\n"
    "/schedule_day <день> — день недели (wed, среда…)\n"
    "/schedule_tz <IANA> — таймзона (Europe/Moscow)"
)

SCHEDULE_PRIVATE_ONLY = "Расписание доступно только в групповых чатах."

SCHEDULE_BACK = "« Назад"

SCHEDULE_NO_SLOTS = "Нет слотов для удаления."

SCHEDULE_SLOT_EXISTS = "Это время уже в расписании."

SCHEDULE_LIMIT_REACHED = "Достигнут лимит расписаний для чата."

SCHEDULE_TRY_LATER = "Слишком много нажатий. Подождите немного."

SCHEDULE_ADD_USAGE = "Использование: /schedule_add ЧЧ:ММ"

SCHEDULE_REMOVE_USAGE = "Использование: /schedule_remove ЧЧ:ММ"

SCHEDULE_DAY_USAGE = "Использование: /schedule_day <день>"

SCHEDULE_TZ_USAGE = "Использование: /schedule_tz <таймзона>"


def weekday_label(weekday: int) -> str:
    return _WEEKDAY_LABELS.get(weekday, str(weekday))


_WEEKDAY_LABELS: dict[int, str] = {
    1: "понедельник",
    2: "вторник",
    3: "среда",
    4: "четверг",
    5: "пятница",
    6: "суббота",
    7: "воскресенье",
}


def _format_time(slot: tuple[int, int]) -> str:
    return f"{slot[0]:02d}:{slot[1]:02d}"


def format_schedule_context(chat: ChatContext) -> str:
    """Format current schedule from registration context."""
    return _format_schedule(
        is_active=chat.is_active,
        weekday=chat.weekday,
        timezone=chat.timezone,
        schedules=chat.schedules,
    )


def _format_schedule(
    *,
    is_active: bool,
    weekday: int,
    timezone: str,
    schedules: list[tuple[int, int]],
) -> str:
    status = "активна" if is_active else "приостановлена"
    day = _WEEKDAY_LABELS.get(weekday, str(weekday))
    if schedules:
        slots = ", ".join(_format_time(slot) for slot in sorted(schedules, key=lambda s: (s[0], s[1])))
    else:
        slots = "нет слотов"
    return f"📅 Расписание чата\n\nРассылка: {status}\nДень: {day}\nТаймзона: {timezone}\nВремена: {slots}"
