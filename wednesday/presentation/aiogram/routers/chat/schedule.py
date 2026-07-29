"""In-chat schedule management commands."""

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.dto import ChatContext
from app.protocols import Logger, RequestScope
from domain.kernel.vo import AwareDatetime

from ...filters import GroupChatFilter, InsufficientCommandArgs, RequireCommandArgs
from ...messages import chat as chat_msg
from ..utils import run_message_handler
from .mappers import resolve_chat_member
from .parsers import parse_schedule_time, parse_timezone, parse_weekday

chat_schedule_router = Router(name="chat_schedule")


@chat_schedule_router.message(Command("schedule"), GroupChatFilter())
async def cmd_schedule(
    message: Message,
    command: CommandObject,
    chat: ChatContext,
    logger: Logger,
) -> None:
    """Show current chat schedule or command help (readable by any group member)."""

    async def _action() -> None:
        args = (command.args or "").split()
        if args and args[0].lower() in {"help", "?"}:
            await message.answer(chat_msg.SCHEDULE_USAGE)
            return
        await message.answer(chat_msg.format_schedule_context(chat))

    await run_message_handler(message, logger, _action)


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
        actor = await resolve_chat_member(bot, message, chat)
        slot = parse_schedule_time(command_args[0])
        updated = await scope.chat_schedule_uc.add_schedule(
            chat_id=chat.id,
            actor=actor,
            schedule=slot,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(chat_msg.format_schedule_chat(updated))

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
        actor = await resolve_chat_member(bot, message, chat)
        slot = parse_schedule_time(command_args[0])
        updated = await scope.chat_schedule_uc.remove_schedule(
            chat_id=chat.id,
            actor=actor,
            schedule=slot,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(chat_msg.format_schedule_chat(updated))

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
        actor = await resolve_chat_member(bot, message, chat)
        updated = await scope.chat_schedule_uc.clear_schedules(
            chat_id=chat.id,
            actor=actor,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(chat_msg.format_schedule_chat(updated))

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
        actor = await resolve_chat_member(bot, message, chat)
        weekday = parse_weekday(command_args[0])
        updated = await scope.chat_schedule_uc.change_schedule_day(
            chat_id=chat.id,
            actor=actor,
            new_weekday=weekday,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(chat_msg.format_schedule_chat(updated))

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
        actor = await resolve_chat_member(bot, message, chat)
        timezone = parse_timezone(command_args[0])
        updated = await scope.chat_schedule_uc.change_schedule_timezone(
            chat_id=chat.id,
            actor=actor,
            timezone=timezone,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(chat_msg.format_schedule_chat(updated))

    await run_message_handler(message, logger, _action)
