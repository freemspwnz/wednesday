"""Inline keyboard for catalog image voting."""

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from domain.image import ImageRating

from ....messages.image import vote_btn_down, vote_btn_up
from .data import ImageVoteData

_VOTE_UP = 1
_VOTE_DOWN = -1


def build_vote_kb(
    *,
    image_id: str,
    rating: ImageRating,
) -> InlineKeyboardMarkup:
    """Build vote row with global likes / dislikes counts."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=vote_btn_up(rating.likes),
                    callback_data=ImageVoteData(image_id=image_id, value=_VOTE_UP).pack(),
                ),
                InlineKeyboardButton(
                    text=vote_btn_down(rating.dislikes),
                    callback_data=ImageVoteData(image_id=image_id, value=_VOTE_DOWN).pack(),
                ),
            ],
        ],
    )


async def edit_vote_markup(
    callback: CallbackQuery,
    *,
    image_id: str,
    rating: ImageRating,
) -> None:
    if not isinstance(callback.message, Message):
        return
    desired = build_vote_kb(image_id=image_id, rating=rating)
    if _same_markup(callback.message.reply_markup, desired):
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=desired)
    except TelegramBadRequest:
        pass


def _same_markup(current: InlineKeyboardMarkup | None, desired: InlineKeyboardMarkup) -> bool:
    if current is None:
        return False
    cur = [[b.text for b in row] for row in current.inline_keyboard]
    new = [[b.text for b in row] for row in desired.inline_keyboard]
    return cur == new
