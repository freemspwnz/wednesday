from datetime import UTC, datetime

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from app.dto import UserContext
from app.protocols import RequestScope

from ...utils import run_callback_handler
from .data import ImageVoteData
from .keyboard import edit_vote_markup

vote_router = Router(name="vote")


@vote_router.callback_query(ImageVoteData.filter())
async def cb_image_vote(
    callback: CallbackQuery,
    callback_data: ImageVoteData,
    user: UserContext,
    scope: RequestScope,
) -> None:
    """Record a vote and refresh likes / dislikes on the keyboard."""

    async def _action() -> None:
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        message = callback.message
        at = datetime.now(UTC)
        private_chat = await scope.chat_management_uc.register(
            tg_id=user.tg_id,
            type="private",
            title=message.chat.title,
            username=message.chat.username,
            at=at,
        )
        card = await scope.image_vote_uc.vote(
            image_id=callback_data.image_id,
            voter_id=user.id,
            chat_id=private_chat.id,
            value=callback_data.value,
            at=at,
        )
        if card is not None:
            await edit_vote_markup(
                callback,
                image_id=callback_data.image_id,
                likes=card.likes,
                dislikes=card.dislikes,
            )
        await callback.answer()

    await run_callback_handler(callback, scope.logger, _action)
