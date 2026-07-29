"""User-facing texts for the user router (profile, models, admin)."""

from . import admin
from .user import (
    LIST_MODELS_EMPTY,
    LIST_MODELS_FOOTER,
    LIST_MODELS_HEADER,
    SET_MODEL_USAGE,
    format_list_models,
    format_me,
    format_set_model_success,
)

__all__ = [
    "LIST_MODELS_EMPTY",
    "LIST_MODELS_FOOTER",
    "LIST_MODELS_HEADER",
    "SET_MODEL_USAGE",
    "admin",
    "format_list_models",
    "format_me",
    "format_set_model_success",
]
