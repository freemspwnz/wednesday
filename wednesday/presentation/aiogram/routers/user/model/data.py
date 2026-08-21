"""Inline callback data for model selection."""

from aiogram.filters.callback_data import CallbackData

# Empty model marks the "Закрыть" button (model codes are never empty).
CLOSE_MODEL = ""


class ModelSelectionData(CallbackData, prefix="mdl"):
    """Payload: model code (+ display_name for success text), or empty model to close."""

    model: str = CLOSE_MODEL
    display_name: str = ""
