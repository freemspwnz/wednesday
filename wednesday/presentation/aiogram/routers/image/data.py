"""Inline callback handler data for catalog image voting."""

from aiogram.filters.callback_data import CallbackData


class ImageVoteData(CallbackData, prefix="imgvote"):
    image_id: str
    value: int
