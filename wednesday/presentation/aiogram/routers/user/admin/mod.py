"""Admin moderation handlers (role changes).

Admin access is enforced by AdminAccessFilter on the parent admin router.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import UserContext
from app.protocols import Logger, RequestScope
from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

from ....filters import InsufficientCommandArgs, RequireCommandArgs
from ....messages import common as common_msg, exceptions as exc_msg
from ....messages.user import admin as admin_msg
from ...utils import parse_telegram_id, run_message_handler

mod_router = Router(name="mod")


@mod_router.message(Command("mod"), InsufficientCommandArgs())
async def cmd_mod_usage(message: Message) -> None:
    await message.answer(admin_msg.MOD_USAGE)


@mod_router.message(Command("mod"), RequireCommandArgs())
async def cmd_mod(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Promote user to admin (domain management policy)."""

    async def _action() -> None:
        target = await scope.user_lifecycle_uc.find_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        await scope.user_management_uc.change_role(
            user_id=target.id,
            actor=user.role,
            new_role=UserRole.ADMIN,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(admin_msg.USER_PROMOTED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)


@mod_router.message(Command("unmod"), InsufficientCommandArgs())
async def cmd_unmod_usage(message: Message) -> None:
    await message.answer(admin_msg.UNMOD_USAGE)


@mod_router.message(Command("unmod"), RequireCommandArgs())
async def cmd_unmod(
    message: Message,
    command_args: list[str],
    logger: Logger,
    scope: RequestScope,
    user: UserContext,
) -> None:
    """Revoke admin role."""

    async def _action() -> None:
        target = await scope.user_lifecycle_uc.find_by_tg_id(
            tg_id=parse_telegram_id(command_args[0]),
        )
        if target is None:
            await message.answer(exc_msg.USER_NOT_FOUND)
            return
        await scope.user_management_uc.change_role(
            user_id=target.id,
            actor=user.role,
            new_role=UserRole.USER,
            at=AwareDatetime.now_utc(),
        )
        await message.answer(admin_msg.USER_DEMOTED.format(tg_id=target.tg_id))

    await run_message_handler(message, logger, _action)


@mod_router.message(Command("list_mods"))
async def cmd_list_mods(message: Message) -> None:
    """List administrators (admin)."""
    await message.answer(common_msg.WIP)
