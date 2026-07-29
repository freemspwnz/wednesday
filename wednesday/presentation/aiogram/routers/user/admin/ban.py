from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import UserContext
from app.protocols import Logger, RequestScope
from domain.kernel.vo import AwareDatetime

from ....filters import InsufficientCommandArgs, RequireCommandArgs
from ....messages import exceptions as exc_msg
from ....messages.user import admin as admin_msg
from ...utils import parse_positive_int, parse_telegram_id, run_message_handler

ban_router = Router(name="ban")


@ban_router.message(Command("ban"), InsufficientCommandArgs(min_count=2))
async def cmd_ban_usage(message: Message) -> None:
    await message.answer(admin_msg.BAN_USAGE)


@ban_router.message(Command("ban"), RequireCommandArgs(min_count=2))
async def cmd_ban(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Ban user: /ban <telegram_id> <days>."""

    async def _action() -> None:
        tg_user_id = parse_telegram_id(command_args[0])
        days = parse_positive_int(command_args[1])
        target = await scope.user_lifecycle_uc.find_by_tg_id(tg_id=tg_user_id)
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        now = AwareDatetime.now_utc()
        until = now + timedelta(days=days)
        await scope.user_moderation_uc.ban(
            user_id=target.id,
            actor=user.role,
            until=until,
            at=now,
        )
        await message.answer(admin_msg.USER_BANNED.format(tg_id=target.tg_id, days=days))

    await run_message_handler(message, logger, _action)


@ban_router.message(Command("unban"), InsufficientCommandArgs())
async def cmd_unban_usage(message: Message) -> None:
    await message.answer(admin_msg.UNBAN_USAGE)


@ban_router.message(Command("unban"), RequireCommandArgs())
async def cmd_unban(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Unban user."""

    async def _action() -> None:
        target = await scope.user_lifecycle_uc.find_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        await scope.user_moderation_uc.unban(
            user_id=target.id,
            actor=user.role,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(admin_msg.USER_UNBANNED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)
