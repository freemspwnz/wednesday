"""Admin command handlers.

Admin access is enforced by AdminAccessFilter on the router (ADMIN or OWNER role).
"""

from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import UserContext
from app.protocols import Logger, RequestScope
from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

from ..filters import InsufficientCommandArgs, RequireCommandArgs
from ..messages import admin as admin_msg, commands as cmd_msg, exceptions as exc_msg
from .utils import parse_positive_int, parse_telegram_id, run_message_handler

admin_router = Router(name="admin")


@admin_router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Extended bot status (admin)."""
    await message.answer(cmd_msg.WIP)


@admin_router.message(Command("force_send"))
async def cmd_force_send(message: Message) -> None:
    """Force-send to chat(s) or list chats (admin)."""
    await message.answer(cmd_msg.WIP)


@admin_router.message(Command("list_chats"))
async def cmd_list_chats(message: Message) -> None:
    """List active chats (admin)."""
    await message.answer(cmd_msg.WIP)


@admin_router.message(Command("set_limit"), InsufficientCommandArgs())
async def cmd_set_limit_usage(message: Message) -> None:
    await message.answer(admin_msg.SET_LIMIT_USAGE)


@admin_router.message(Command("set_limit"), RequireCommandArgs())
async def cmd_set_limit(message: Message) -> None:
    """Set manual generation limit."""
    await message.answer(cmd_msg.WIP)


@admin_router.message(Command("set_used"), InsufficientCommandArgs())
async def cmd_set_used_usage(message: Message) -> None:
    await message.answer(admin_msg.SET_USED_USAGE)


@admin_router.message(Command("set_used"), RequireCommandArgs())
async def cmd_set_used(message: Message) -> None:
    """Set current manual generation usage."""
    await message.answer(cmd_msg.WIP)


@admin_router.message(Command("mod"), InsufficientCommandArgs())
async def cmd_mod_usage(message: Message) -> None:
    await message.answer(admin_msg.MOD_USAGE)


@admin_router.message(Command("mod"), RequireCommandArgs())
async def cmd_mod(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Promote user to admin (domain management policy)."""

    async def _action() -> None:
        target = await scope.registration_uc.find_user_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        await scope.user_commands_uc.change_role(
            user_id=target.id,
            actor=user.role,
            new_role=UserRole.ADMIN,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(admin_msg.USER_PROMOTED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)


@admin_router.message(Command("unmod"), InsufficientCommandArgs())
async def cmd_unmod_usage(message: Message) -> None:
    await message.answer(admin_msg.UNMOD_USAGE)


@admin_router.message(Command("unmod"), RequireCommandArgs())
async def cmd_unmod(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Revoke admin role (domain management policy)."""

    async def _action() -> None:
        target = await scope.registration_uc.find_user_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        await scope.user_commands_uc.change_role(
            user_id=target.id,
            actor=user.role,
            new_role=UserRole.USER,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(admin_msg.USER_DEMOTED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)


@admin_router.message(Command("list_mods"))
async def cmd_list_mods(message: Message) -> None:
    """List administrators (admin)."""
    await message.answer(cmd_msg.WIP)


@admin_router.message(Command("ban"), InsufficientCommandArgs(min_count=2))
async def cmd_ban_usage(message: Message) -> None:
    await message.answer(admin_msg.BAN_USAGE)


@admin_router.message(Command("ban"), RequireCommandArgs(min_count=2))
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
        target = await scope.registration_uc.find_user_by_tg_id(tg_id=tg_user_id)
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        now = AwareDatetime.now_utc()
        until = now + timedelta(days=days)
        await scope.user_commands_uc.ban(
            user_id=target.id,
            actor=user.role,
            until=until,
            at=now,
        )
        await message.answer(admin_msg.USER_BANNED.format(tg_id=target.tg_id, days=days))

    await run_message_handler(message, logger, _action)


@admin_router.message(Command("unban"), InsufficientCommandArgs())
async def cmd_unban_usage(message: Message) -> None:
    await message.answer(admin_msg.UNBAN_USAGE)


@admin_router.message(Command("unban"), RequireCommandArgs())
async def cmd_unban(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Unban user."""

    async def _action() -> None:
        target = await scope.registration_uc.find_user_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        await scope.user_commands_uc.unban(
            user_id=target.id,
            actor=user.role,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(admin_msg.USER_UNBANNED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)
