"""User-facing model command texts."""

from collections.abc import Sequence

SET_MODEL_USAGE = "Использование: /set_model <модель>"

LIST_MODELS_EMPTY = "Нет доступных моделей для вашей подписки."

LIST_MODELS_HEADER = "Доступные модели:"

LIST_MODELS_FOOTER = "Выбор: /set_model <код модели>"

MODELS_PROMPT = "Выберите модель:"

MODELS_CANCELLED = "Выберите модель: отменено"

MODELS_ALREADY_ACTIVE = "Эта модель уже активна"

MODELS_EMPTY = LIST_MODELS_EMPTY


def format_set_model_success(model: str) -> str:
    return f"✅ Модель изменена: {model}"


def format_list_models(models: Sequence[str]) -> str:
    if not models:
        return LIST_MODELS_EMPTY
    lines = [LIST_MODELS_HEADER, "", *(f"• {model}" for model in models), "", LIST_MODELS_FOOTER]
    return "\n".join(lines)
