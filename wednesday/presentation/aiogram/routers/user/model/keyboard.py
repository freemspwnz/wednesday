"""Inline keyboard for model selection."""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .data import CLOSE_MODEL, ModelSelectionData

_CURRENT_MARK = "✅ "
_CLOSE_LABEL = "Закрыть"


def build_models_kb(
    items: Sequence[tuple[str, str]],
    *,
    current: str,
) -> InlineKeyboardMarkup:
    """One button per (code, display_name); current marked; close at the bottom."""
    rows: list[list[InlineKeyboardButton]] = [
        [_model_btn(code, display_name, current=current)] for code, display_name in items
    ]
    rows.append([_close_btn()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _model_btn(code: str, display_name: str, *, current: str) -> InlineKeyboardButton:
    mark = _CURRENT_MARK if code == current else ""
    return InlineKeyboardButton(
        text=f"{mark}{display_name}",
        callback_data=ModelSelectionData(model=code).pack(),
    )


def _close_btn() -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=_CLOSE_LABEL,
        callback_data=ModelSelectionData(model=CLOSE_MODEL).pack(),
    )
