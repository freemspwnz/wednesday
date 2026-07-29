"""Handlers for model commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import UserContext
from app.protocols import Logger, RequestScope
from domain.catalog import Model
from domain.kernel.vo import AwareDatetime

from ...filters import InsufficientCommandArgs, RequireCommandArgs
from ...messages import user as user_msg
from ..utils import run_message_handler

model_router = Router(name="model")


@model_router.message(Command("set_model"), InsufficientCommandArgs())
async def cmd_set_model_usage(message: Message) -> None:
    await message.answer(user_msg.SET_MODEL_USAGE)


@model_router.message(Command("set_model"), RequireCommandArgs())
async def cmd_set_model(
    message: Message,
    command_args: list[str],
    user: UserContext,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Set image generation model for the caller."""

    async def _action() -> None:
        updated = await scope.user_generation_uc.select_model(
            user_id=user.id,
            model=Model.parse(command_args[0]),
            at=AwareDatetime.now_utc(),
        )
        await message.answer(user_msg.format_set_model_success(str(updated.settings.model)))

    await run_message_handler(message, logger, _action)


@model_router.message(Command("list_models"))
async def cmd_list_models(
    message: Message,
    user: UserContext,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """List active models available for the caller subscription tier."""

    async def _action() -> None:
        tier = user.subscription_tier
        descriptors = await scope.models.list_active()
        models = sorted(str(d.model) for d in descriptors if d.min_tier <= tier)
        await message.answer(user_msg.format_list_models(models))

    await run_message_handler(message, logger, _action)
