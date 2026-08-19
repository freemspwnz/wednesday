"""Inline callback data for catalog view reset."""

from aiogram.filters.callback_data import CallbackData


class ResetViewsData(CallbackData, prefix="reset_views"):
    confirm: bool
