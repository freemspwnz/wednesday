"""Chat router: membership events and in-chat schedule management."""

import random

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatMemberUpdated, Message

from app.dto import ChatContext
from app.protocols import Logger, RequestScope
from domain.chat import System
from domain.kernel.exceptions import InvalidStateTransitionError
from domain.kernel.vo import AwareDatetime

from ...filters import GroupChatFilter, InsufficientCommandArgs, RequireCommandArgs
from ...messages import chat as chat_msg
from ...middlewares.utils import CHAT_MEMBER_LEFT_STATUSES
from ..utils import run_message_handler
from .mappers import resolve_chat_member
from .parsers import parse_schedule_time, parse_timezone, parse_weekday

chat_router = Router(name="chat")

_GREETING_CHAT_TYPES = frozenset({"group", "supergroup"})


@chat_router.my_chat_member()
async def on_my_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    logger: Logger,
    scope: RequestScope,
) -> None:
    """Bot added/removed to/from chat."""
    log = logger.bind(module="my_chat_member")
    status = event.new_chat_member.status
    log.info("My chat member event", status=status)

    if status in CHAT_MEMBER_LEFT_STATUSES:
        chat = await scope.chat_management_uc.find_by_tg_id(tg_id=event.chat.id)
        if chat is not None:
            try:
                await scope.chat_management_uc.deactivate(
                    chat_id=chat.id,
                    actor=System(),
                    at=AwareDatetime.now_utc(),
                )
                log.info("Chat deactivated after bot left", tg_chat_id=event.chat.id)
            except InvalidStateTransitionError:
                log.debug("Chat already inactive", tg_chat_id=event.chat.id)
            except Exception:
                log.warning(
                    "Failed to deactivate chat after bot left",
                    tg_chat_id=event.chat.id,
                    exc_info=True,
                )
        return

    if status == ChatMemberStatus.MEMBER:
        try:
            await bot.send_message(chat_id=event.chat.id, text=chat_msg.BOT_ADDED_TO_CHAT)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)


@chat_router.chat_member()
async def on_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    logger: Logger,
) -> None:
    """Chat member added/removed greetings."""
    log = logger.bind(module="chat_member")
    status = event.new_chat_member.status
    log.info("Chat member event", status=status)

    if event.chat.type not in _GREETING_CHAT_TYPES:
        return

    if status == ChatMemberStatus.MEMBER:
        text = random.choice(chat_msg.MEMBER_JOINED)
        try:
            await bot.send_message(chat_id=event.chat.id, text=text)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)

    if status in CHAT_MEMBER_LEFT_STATUSES:
        text = random.choice(chat_msg.MEMBER_LEFT)
        try:
            await bot.send_message(chat_id=event.chat.id, text=text)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)


@chat_router.message(Command("schedule"), GroupChatFilter())
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


@chat_router.message(Command("activate"), GroupChatFilter())
async def cmd_activate(
    message: Message,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Enable broadcast for this chat (chat admins via domain policy)."""

    async def _action() -> None:
        actor = await resolve_chat_member(bot, message, chat)
        updated = await scope.chat_management_uc.activate(
            chat_id=chat.id,
            actor=actor,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(chat_msg.format_schedule_chat(updated))

    await run_message_handler(message, logger, _action)


@chat_router.message(Command("deactivate"), GroupChatFilter())
async def cmd_deactivate(
    message: Message,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Pause broadcast for this chat (chat admins via domain policy)."""

    async def _action() -> None:
        actor = await resolve_chat_member(bot, message, chat)
        updated = await scope.chat_management_uc.deactivate(
            chat_id=chat.id,
            actor=actor,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(chat_msg.format_schedule_chat(updated))

    await run_message_handler(message, logger, _action)


@chat_router.message(Command("schedule_add"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_add_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_ADD_USAGE)


@chat_router.message(Command("schedule_add"), GroupChatFilter(), RequireCommandArgs())
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


@chat_router.message(Command("schedule_remove"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_remove_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_REMOVE_USAGE)


@chat_router.message(Command("schedule_remove"), GroupChatFilter(), RequireCommandArgs())
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


@chat_router.message(Command("schedule_clear"), GroupChatFilter())
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


@chat_router.message(Command("schedule_day"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_day_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_DAY_USAGE)


@chat_router.message(Command("schedule_day"), GroupChatFilter(), RequireCommandArgs())
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


@chat_router.message(Command("schedule_tz"), GroupChatFilter(), InsufficientCommandArgs())
async def cmd_schedule_tz_usage(message: Message) -> None:
    await message.answer(chat_msg.SCHEDULE_TZ_USAGE)


@chat_router.message(Command("schedule_tz"), GroupChatFilter(), RequireCommandArgs())
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
