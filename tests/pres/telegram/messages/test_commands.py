import pytest

from presentation.aiogram.messages import common as common_msg, user as user_msg


@pytest.mark.unit
def test_format_set_model_success() -> None:
    assert user_msg.format_set_model_success("gigachat-2-pro") == "✅ Модель изменена: gigachat-2-pro"


@pytest.mark.unit
def test_format_list_models_empty() -> None:
    assert user_msg.format_list_models([]) == user_msg.LIST_MODELS_EMPTY


@pytest.mark.unit
def test_format_list_models_with_items() -> None:
    text = user_msg.format_list_models(["gigachat-2-lite", "gigachat-2-pro"])
    assert user_msg.LIST_MODELS_HEADER in text
    assert "• gigachat-2-lite" in text
    assert "• gigachat-2-pro" in text
    assert user_msg.LIST_MODELS_FOOTER in text


@pytest.mark.unit
def test_bot_commands_include_models_not_legacy() -> None:
    commands = {item.command for item in common_msg.BOT_COMMANDS}
    assert "models" in commands
    assert "random" in commands
    assert "set_model" not in commands
    assert "list_models" not in commands


@pytest.mark.unit
def test_help_mentions_models_not_legacy() -> None:
    assert "/models" in common_msg.HELP
    assert "/set_model" not in common_msg.HELP
    assert "/list_models" not in common_msg.HELP
