"""In-chat schedule management: text CRUD + inline menu."""

from datetime import UTC, datetime

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.dto import ChatContext
from app.protocols import Logger, RequestScope

from ....filters import GroupChatFilter, InsufficientCommandArgs, RequireCommandArgs
from ....messages import chat as chat_msg, common as common_msg
from ...utils import run_callback_handler, run_message_handler
from ..mappers import resolve_chat_member
from ..parsers import parse_schedule_time, parse_timezone, parse_weekday
from .data import ScheduleData
from .keyboard import (
    TIMEZONE_PRESETS,
    build_day_kb,
    build_main_kb,
    build_slots_kb,
    build_status_kb,
    build_tz_kb,
)

chat_schedule_router = Router(name="chat_schedule")

_GROUP_TYPES = frozenset({"group", "supergroup"})
_WEEKDAY_MIN = 1
_WEEKDAY_MAX = 7


@chat_schedule_router.message(Command("schedule"))
async def cmd_schedule(
    message: Message,
    command: CommandObject,
    chat: ChatContext,
    logger: Logger,
) -> None:
    """Show schedule UI in groups; explain private limitation elsewhere."""

    async def _action() -> None:
        args = (command.args or "").split()
        if args and args[0].lower() in {"help", "?"}:
            await message.answer(chat_msg.SCHEDULE_USAGE)
            return
        if chat.type not in _GROUP_TYPES:
            await message.answer(chat_msg.SCHEDULE_PRIVATE_ONLY)
            return
        await message.answer(
            chat_msg.format_schedule_context(chat),
            reply_markup=build_main_kb(chat),
        )

    await run_message_handler(message, logger, _action)


@chat_schedule_router.callback_query(ScheduleData.filter())
async def cb_schedule(
    callback: CallbackQuery,
    callback_data: ScheduleData,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
) -> None:
    """Navigate schedule menu and apply day / timezone / active mutations."""

    async def _action() -> None:
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        if chat.type not in _GROUP_TYPES:
            await callback.answer(chat_msg.SCHEDULE_PRIVATE_ONLY, show_alert=True)
            return

        action = callback_data.action
        if action == "menu":
            await _show_main(callback, chat)
            return
        if action == "open":
            markup = _open_submenu(callback_data.value, chat)
            if markup is None:
                await callback.answer()
                return
            await callback.message.edit_reply_markup(reply_markup=markup)
            await callback.answer()
            return
        if action == "status":
            updated = await _apply_status(callback, bot, scope, chat, callback_data.value)
            await _show_main(callback, updated)
            return
        if action == "day":
            updated = await _apply_day(callback, bot, scope, chat, callback_data.value)
            await _show_main(callback, updated)
            return
        if action == "tz":
            updated = await _apply_tz(callback, bot, scope, chat, callback_data.value)
            await _show_main(callback, updated)
            return
        if action == "stub":
            await callback.answer(common_msg.WIP)
            return
        await callback.answer()

    await run_callback_handler(callback, scope.logger, _action)


def _open_submenu(value: str, chat: ChatContext) -> InlineKeyboardMarkup | None:
    if value == "status":
        return build_status_kb(is_active=chat.is_active)
    if value == "day":
        return build_day_kb(current=chat.weekday)
    if value == "tz":
        return build_tz_kb(current=chat.timezone)
    if value == "slots":
        return build_slots_kb()
    return None


async def _show_main(callback: CallbackQuery, chat: ChatContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await callback.message.edit_text(
        chat_msg.format_schedule_context(chat),
        reply_markup=build_main_kb(chat),
    )
    await callback.answer()


async def _apply_status(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    if value == "on":
        return await scope.chat_management_uc.activate(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            at=at,
        )
    if value == "off":
        return await scope.chat_management_uc.deactivate(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            at=at,
        )
    msg = "Неизвестное действие для рассылки."
    raise ValueError(msg)


async def _apply_day(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    try:
        weekday = int(value)
    except ValueError as exc:
        msg = "Некорректный день недели."
        raise ValueError(msg) from exc
    if weekday < _WEEKDAY_MIN or weekday > _WEEKDAY_MAX:
        msg = "Некорректный день недели."
        raise ValueError(msg)
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.change_schedule_day(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        new_weekday=weekday,
        at=at,
    )


async def _apply_tz(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    try:
        index = int(value)
        timezone = TIMEZONE_PRESETS[index]
    except (ValueError, IndexError) as exc:
        msg = "Некорректная таймзона."
        raise ValueError(msg) from exc
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.change_schedule_timezone(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        timezone=timezone,
        at=at,
    )


@chat_schedule_router.message(Command("schedule_add"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_add_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_ADD_USAGE)


@chat_schedule_router.message(Command("schedule_add"), GroupChatFilter(), RequireCommandArgs())
async def cmd_schedule_add(  # noqa: PLR0913, PLR0917
    message: Message,
    command_args: list[str],
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Add a send time slot."""

    async def _action() -> None:
        at = message.date
        actor_id, actor_role = await resolve_chat_member(bot, message, chat)
        slot = parse_schedule_time(command_args[0])
        updated = await scope.chat_schedule_uc.add_schedule(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            schedule=slot,
            at=at,
        )
        await message.answer(chat_msg.format_schedule_context(updated))

    await run_message_handler(message, logger, _action)


@chat_schedule_router.message(Command("schedule_remove"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_remove_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_REMOVE_USAGE)


@chat_schedule_router.message(Command("schedule_remove"), GroupChatFilter(), RequireCommandArgs())
async def cmd_schedule_remove(  # noqa: PLR0913, PLR0917
    message: Message,
    command_args: list[str],
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Remove a send time slot."""

    async def _action() -> None:
        at = message.date
        actor_id, actor_role = await resolve_chat_member(bot, message, chat)
        slot = parse_schedule_time(command_args[0])
        updated = await scope.chat_schedule_uc.remove_schedule(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            schedule=slot,
            at=at,
        )
        await message.answer(chat_msg.format_schedule_context(updated))

    await run_message_handler(message, logger, _action)


@chat_schedule_router.message(Command("schedule_clear"), GroupChatFilter())
async def cmd_schedule_clear(
    message: Message,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Clear all schedule slots."""

    async def _action() -> None:
        at = message.date
        actor_id, actor_role = await resolve_chat_member(bot, message, chat)
        updated = await scope.chat_schedule_uc.clear_schedules(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            at=at,
        )
        await message.answer(chat_msg.format_schedule_context(updated))

    await run_message_handler(message, logger, _action)


@chat_schedule_router.message(Command("schedule_day"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_day_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_DAY_USAGE)


@chat_schedule_router.message(Command("schedule_day"), GroupChatFilter(), RequireCommandArgs())
async def cmd_schedule_day(  # noqa: PLR0913, PLR0917
    message: Message,
    command_args: list[str],
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Change schedule weekday."""

    async def _action() -> None:
        at = message.date
        actor_id, actor_role = await resolve_chat_member(bot, message, chat)
        weekday = parse_weekday(command_args[0])
        updated = await scope.chat_schedule_uc.change_schedule_day(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            new_weekday=weekday,
            at=at,
        )
        await message.answer(chat_msg.format_schedule_context(updated))

    await run_message_handler(message, logger, _action)


@chat_schedule_router.message(Command("schedule_tz"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_tz_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_TZ_USAGE)


@chat_schedule_router.message(Command("schedule_tz"), GroupChatFilter(), RequireCommandArgs())
async def cmd_schedule_tz(  # noqa: PLR0913, PLR0917
    message: Message,
    command_args: list[str],
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Change schedule timezone."""

    async def _action() -> None:
        at = message.date
        actor_id, actor_role = await resolve_chat_member(bot, message, chat)
        timezone = parse_timezone(command_args[0])
        updated = await scope.chat_schedule_uc.change_schedule_timezone(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            timezone=timezone,
            at=at,
        )
        await message.answer(chat_msg.format_schedule_context(updated))

    await run_message_handler(message, logger, _action)
