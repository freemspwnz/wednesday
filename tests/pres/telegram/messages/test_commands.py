from __future__ import annotations

import pytest

from presentation.aiogram.messages import commands as cmd_msg


@pytest.mark.unit
def test_format_set_model_success() -> None:
    assert cmd_msg.format_set_model_success("gigachat-2-pro") == "✅ Модель изменена: gigachat-2-pro"


@pytest.mark.unit
def test_format_list_models_empty() -> None:
    assert cmd_msg.format_list_models([]) == cmd_msg.LIST_MODELS_EMPTY


@pytest.mark.unit
def test_format_list_models_with_items() -> None:
    text = cmd_msg.format_list_models(["gigachat-2-lite", "gigachat-2-pro"])
    assert cmd_msg.LIST_MODELS_HEADER in text
    assert "• gigachat-2-lite" in text
    assert "• gigachat-2-pro" in text
    assert cmd_msg.LIST_MODELS_FOOTER in text


@pytest.mark.unit
def test_bot_commands_include_random() -> None:
    commands = {item.command for item in cmd_msg.BOT_COMMANDS}
    assert "random" in commands
