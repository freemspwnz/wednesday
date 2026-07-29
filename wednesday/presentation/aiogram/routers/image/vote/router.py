from uuid import UUID

from aiogram import Router
from aiogram.types import CallbackQuery

from app.dto import UserContext
from app.protocols import RequestScope
from domain.image import ImageId
from domain.kernel.vo import AwareDatetime

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
        card = await scope.image_vote_uc.vote(
            image_id=ImageId(UUID(callback_data.image_id)),
            voter_id=user.id,
            value=callback_data.value,
            at=AwareDatetime.now_utc(),
        )
        if card is not None:
            await edit_vote_markup(
                callback,
                image_id=callback_data.image_id,
                rating=card.rating,
            )
        await callback.answer()

    await run_callback_handler(callback, scope.logger, _action)
