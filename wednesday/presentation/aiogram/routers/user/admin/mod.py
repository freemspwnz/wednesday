"""Admin moderation handlers (role changes).

Admin access is enforced by AdminAccessFilter on the parent admin router.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import UserContext
from app.protocols import Logger, RequestScope
from presentation.aiogram.errors.messages import USER_NOT_FOUND
from presentation.aiogram.filters import InsufficientCommandArgs, RequireCommandArgs

from ...utils import parse_telegram_id, run_message_handler
from . import messages as admin_msg

mod_router = Router(name="mod")


@mod_router.message(Command("promote"), InsufficientCommandArgs())
async def cmd_promote_usage(message: Message) -> None:
    await message.answer(admin_msg.PROMOTE_USAGE)


@mod_router.message(Command("promote"), RequireCommandArgs())
async def cmd_promote(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Promote user to admin (domain management policy)."""

    async def _action() -> None:
        at = message.date
        target = await scope.user_lifecycle_uc.find_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(USER_NOT_FOUND)
            return
        await scope.user_management_uc.change_role(
            user_id=target.id,
            actor=user.role,
            action="promote",
            at=at,
        )
        await message.answer(admin_msg.USER_PROMOTED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)


@mod_router.message(Command("demote"), InsufficientCommandArgs())
async def cmd_demote_usage(message: Message) -> None:
    await message.answer(admin_msg.DEMOTE_USAGE)


@mod_router.message(Command("demote"), RequireCommandArgs())
async def cmd_demote(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Revoke admin role."""

    async def _action() -> None:
        at = message.date
        target = await scope.user_lifecycle_uc.find_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(USER_NOT_FOUND)
            return
        await scope.user_management_uc.change_role(
            user_id=target.id,
            actor=user.role,
            action="demote",
            at=at,
        )
        await message.answer(admin_msg.USER_DEMOTED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)


@mod_router.message(Command("list_mods"))
async def cmd_list_mods(message: Message) -> None:
    """List administrators (admin)."""
    await message.answer(admin_msg.WIP)
