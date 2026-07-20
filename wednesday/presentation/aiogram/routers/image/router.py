"""Image catalog router."""

from uuid import UUID

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.dto import ChatContext, UserContext
from app.protocols import Logger, RequestScope
from domain.image import ImageId
from domain.kernel.vo import AwareDatetime

from ...messages import commands as cmd_msg
from ..utils import run_callback_handler, run_message_handler
from .data import ImageVoteData
from .keyboard import build_vote_kb

image_router = Router(name="image")


@image_router.callback_query(ImageVoteData.filter())
async def cb_image_vote(
    callback: CallbackQuery,
    callback_data: ImageVoteData,
    user: UserContext,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Record a vote for a catalog image."""

    async def _action() -> None:
        await scope.image_vote_uc.vote(
            image_id=ImageId(UUID(callback_data.image_id)),
            voter_id=user.id.value,
            value=callback_data.value,
            at=AwareDatetime.now_utc(),
        )
        await callback.answer()

    await run_callback_handler(callback, logger, _action)


@image_router.message(Command("random"))
async def cmd_random(
    message: Message,
    chat: ChatContext,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Send a random unseen catalog image for the current chat."""

    async def _action() -> None:
        card = await scope.image_catalog_uc.pick_for_chat(
            chat_id=chat.id.value,
            at=AwareDatetime.now_utc(),
        )
        if card is None:
            await message.answer(cmd_msg.RANDOM_CATALOG_EMPTY)
            return

        await message.answer_photo(
            photo=str(card.file_id),
            reply_markup=build_vote_kb(image_id=card.id),
        )

    await run_message_handler(message, logger, _action)


@image_router.message(Command("generate"))
async def cmd_generate(message: Message) -> None:
    """Start image generation: status message and enqueue."""
    await message.answer(text=cmd_msg.WIP)
