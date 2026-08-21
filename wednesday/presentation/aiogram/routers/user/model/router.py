"""Handlers for model commands and inline picker."""

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.dto import UserContext
from app.protocols import Logger, RequestScope

from ....filters import InsufficientCommandArgs, RequireCommandArgs
from ....messages import user as user_msg
from ...utils import run_callback_handler, run_message_handler, safe_callback_answer
from .data import CLOSE_MODEL, ModelSelectionData
from .keyboard import build_models_kb

model_router = Router(name="model")


@model_router.message(Command("models"))
async def cmd_models(
    message: Message,
    user: UserContext,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Show inline model picker for the caller's subscription tier."""

    async def _action() -> None:
        items = await scope.user_generation_uc.list_selectable_models(
            subscription_tier=user.subscription_tier,
        )
        if not items:
            await message.answer(user_msg.MODELS_EMPTY)
            return
        await message.answer(
            user_msg.MODELS_PROMPT,
            reply_markup=build_models_kb(items, current=user.model),
        )

    await run_message_handler(message, logger, _action)


@model_router.callback_query(ModelSelectionData.filter())
async def cb_select_model(
    callback: CallbackQuery,
    callback_data: ModelSelectionData,
    user: UserContext,
    scope: RequestScope,
) -> None:
    """Select a model, reject already-active, or close the picker."""

    async def _action() -> None:
        if not isinstance(callback.message, Message):
            await safe_callback_answer(callback)
            return

        if callback_data.model == CLOSE_MODEL:
            await _edit_picker(callback.message, user_msg.MODELS_CANCELLED)
            await safe_callback_answer(callback)
            return

        if callback_data.model == user.model:
            await safe_callback_answer(callback, user_msg.MODELS_ALREADY_ACTIVE)
            return

        at = callback.message.date
        updated = await scope.user_generation_uc.select_model(
            user_id=user.id,
            model=callback_data.model,
            at=at,
        )
        await _edit_picker(callback.message, user_msg.format_set_model_success(updated.model))
        await safe_callback_answer(callback)

    await run_callback_handler(callback, scope.logger, _action)


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
    """Set image generation model for the caller (legacy / power-user)."""

    async def _action() -> None:
        at = message.date
        updated = await scope.user_generation_uc.select_model(
            user_id=user.id,
            model=command_args[0].lower(),
            at=at,
        )
        await message.answer(user_msg.format_set_model_success(updated.model))

    await run_message_handler(message, logger, _action)


@model_router.message(Command("list_models"))
async def cmd_list_models(
    message: Message,
    user: UserContext,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """List active models available for the caller subscription tier (legacy)."""

    async def _action() -> None:
        items = await scope.user_generation_uc.list_selectable_models(
            subscription_tier=user.subscription_tier,
        )
        await message.answer(user_msg.format_list_models([code for code, _ in items]))

    await run_message_handler(message, logger, _action)


async def _edit_picker(message: Message, text: str) -> None:
    try:
        await message.edit_text(text, reply_markup=None)
    except TelegramBadRequest:
        return
