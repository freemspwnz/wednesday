"""Inline keyboard for catalog image voting."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from domain.image import ImageId

from .data import ImageVoteData


def build_vote_kb(*, image_id: ImageId) -> InlineKeyboardMarkup:
    image_key = str(image_id.value)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👍",
                    callback_data=ImageVoteData(image_id=image_key, value=1).pack(),
                ),
                InlineKeyboardButton(
                    text="👎",
                    callback_data=ImageVoteData(image_id=image_key, value=-1).pack(),
                ),
            ],
        ],
    )
