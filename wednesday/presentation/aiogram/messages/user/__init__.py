"""User-facing texts for the user router (profile, models, admin)."""

from . import admin
from .user import (
    LIST_MODELS_EMPTY,
    LIST_MODELS_FOOTER,
    LIST_MODELS_HEADER,
    MODELS_ALREADY_ACTIVE,
    MODELS_CANCELLED,
    MODELS_EMPTY,
    MODELS_PROMPT,
    SET_MODEL_USAGE,
    format_list_models,
    format_me,
    format_model_selected,
    format_set_model_success,
)

__all__ = [
    "LIST_MODELS_EMPTY",
    "LIST_MODELS_FOOTER",
    "LIST_MODELS_HEADER",
    "MODELS_ALREADY_ACTIVE",
    "MODELS_CANCELLED",
    "MODELS_EMPTY",
    "MODELS_PROMPT",
    "SET_MODEL_USAGE",
    "admin",
    "format_list_models",
    "format_me",
    "format_model_selected",
    "format_set_model_success",
]
