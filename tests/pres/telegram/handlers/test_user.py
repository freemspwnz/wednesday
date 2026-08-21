"""Tests for user router handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message

from app.dto import UserContext
from domain.user.exceptions import ModelNotFoundError, ModelSelectionError
from presentation.aiogram.messages import exceptions as exc_msg, user as user_msg
from presentation.aiogram.routers import user as handlers
from presentation.aiogram.routers.user.model.data import CLOSE_MODEL, ModelSelectionData
from presentation.aiogram.routers.user.model.keyboard import build_models_kb

from ..factories import make_callback_query, make_message, mk_user_context


@pytest.fixture
def user_context() -> UserContext:
    return mk_user_context()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_me_replies_with_profile(user_context: UserContext) -> None:
    message = make_message(text="/me")
    expected = user_msg.format_me(user_context)
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_me(message, user_context)
    answer.assert_awaited_once_with(text=expected)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_usage() -> None:
    message = make_message(text="/set_model")
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model_usage(message)
    answer.assert_awaited_once_with(user_msg.SET_MODEL_USAGE)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_success(user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    updated = mk_user_context()
    mock_scope.user_generation_uc.select_model = AsyncMock(return_value=updated)
    message = make_message(text="/set_model gigachat-2-lite")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model(
            message,
            ["gigachat-2-lite"],
            user_context,
            mock_scope,
            mock_logger,
        )

    mock_scope.user_generation_uc.select_model.assert_awaited_once()
    answer.assert_awaited_once_with(user_msg.format_set_model_success("gigachat-2-lite"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_not_found(user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    mock_scope.user_generation_uc.select_model = AsyncMock(
        side_effect=ModelNotFoundError("missing-model"),
    )
    message = make_message(text="/set_model missing-model")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model(
            message,
            ["missing-model"],
            user_context,
            mock_scope,
            mock_logger,
        )

    answer.assert_awaited_once_with(exc_msg.MODEL_NOT_FOUND)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_tier_denied(user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    mock_scope.user_generation_uc.select_model = AsyncMock(
        side_effect=ModelSelectionError("tier_too_low"),
    )
    message = make_message(text="/set_model gigachat-2-pro")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model(
            message,
            ["gigachat-2-pro"],
            user_context,
            mock_scope,
            mock_logger,
        )

    answer.assert_awaited_once_with("Модель недоступна для вашей подписки.")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_models_filters_by_tier(
    user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock
) -> None:
    mock_scope.user_generation_uc.list_selectable_models = AsyncMock(
        return_value=[("gigachat-2-lite", "GigaChat 2 Lite")],
    )
    message = make_message(text="/list_models")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_list_models(message, user_context, mock_scope, mock_logger)

    answer.assert_awaited_once_with(user_msg.format_list_models(["gigachat-2-lite"]))
    mock_scope.user_generation_uc.list_selectable_models.assert_awaited_once_with(
        subscription_tier=user_context.subscription_tier,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_models_empty_for_tier(
    user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock
) -> None:
    mock_scope.user_generation_uc.list_selectable_models = AsyncMock(return_value=[])
    message = make_message(text="/list_models")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_list_models(message, user_context, mock_scope, mock_logger)

    answer.assert_awaited_once_with(user_msg.LIST_MODELS_EMPTY)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_models_sends_prompt_and_keyboard(
    user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock
) -> None:
    items = [
        ("gigachat-2-lite", "GigaChat 2 Lite"),
        ("gigachat-2-pro", "GigaChat 2 Pro"),
    ]
    mock_scope.user_generation_uc.list_selectable_models = AsyncMock(return_value=items)
    message = make_message(text="/models")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_models(message, user_context, mock_scope, mock_logger)

    answer.assert_awaited_once()
    assert answer.await_args is not None
    assert answer.await_args.args[0] == user_msg.MODELS_PROMPT
    markup = answer.await_args.kwargs["reply_markup"]
    assert markup == build_models_kb(items, current=user_context.model)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_models_empty(user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    mock_scope.user_generation_uc.list_selectable_models = AsyncMock(return_value=[])
    message = make_message(text="/models")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_models(message, user_context, mock_scope, mock_logger)

    answer.assert_awaited_once_with(user_msg.MODELS_EMPTY)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_select_model_success(user_context: UserContext, mock_scope: MagicMock) -> None:
    mock_scope.user_generation_uc.select_model = AsyncMock(return_value=user_context)
    payload = ModelSelectionData(model="gigachat-2-pro", display_name="GigaChat 2 Pro")
    callback = make_callback_query(data=payload.pack())

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as cb_answer,
        patch.object(Message, "edit_text", new_callable=AsyncMock) as edit_text,
    ):
        await handlers.cb_select_model(callback, payload, user_context, mock_scope)

    mock_scope.user_generation_uc.select_model.assert_awaited_once()
    edit_text.assert_awaited_once_with(
        user_msg.format_model_selected("GigaChat 2 Pro"),
        reply_markup=None,
    )
    cb_answer.assert_awaited_once_with()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_select_model_already_active(user_context: UserContext, mock_scope: MagicMock) -> None:
    payload = ModelSelectionData(model=user_context.model, display_name="Current")
    callback = make_callback_query(data=payload.pack())

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as cb_answer,
        patch.object(Message, "edit_text", new_callable=AsyncMock) as edit_text,
    ):
        await handlers.cb_select_model(callback, payload, user_context, mock_scope)

    mock_scope.user_generation_uc.select_model.assert_not_called()
    edit_text.assert_not_awaited()
    cb_answer.assert_awaited_once_with(user_msg.MODELS_ALREADY_ACTIVE, show_alert=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_select_model_tier_denied(user_context: UserContext, mock_scope: MagicMock) -> None:
    mock_scope.user_generation_uc.select_model = AsyncMock(
        side_effect=ModelSelectionError("tier_too_low"),
    )
    payload = ModelSelectionData(model="gigachat-2-pro", display_name="GigaChat 2 Pro")
    callback = make_callback_query(data=payload.pack())

    with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as cb_answer:
        await handlers.cb_select_model(callback, payload, user_context, mock_scope)

    cb_answer.assert_awaited_once_with("Модель недоступна для вашей подписки.", show_alert=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_select_model_close(user_context: UserContext, mock_scope: MagicMock) -> None:
    payload = ModelSelectionData(model=CLOSE_MODEL)
    callback = make_callback_query(data=payload.pack())

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as cb_answer,
        patch.object(Message, "edit_text", new_callable=AsyncMock) as edit_text,
    ):
        await handlers.cb_select_model(callback, payload, user_context, mock_scope)

    mock_scope.user_generation_uc.select_model.assert_not_called()
    edit_text.assert_awaited_once_with(user_msg.MODELS_CANCELLED, reply_markup=None)
    cb_answer.assert_awaited_once_with()


@pytest.mark.unit
def test_build_models_kb_marks_current_and_packs_display_name() -> None:
    kb = build_models_kb(
        [("gigachat-2-lite", "GigaChat 2 Lite"), ("gigachat-2-pro", "GigaChat 2 Pro")],
        current="gigachat-2-lite",
    )
    rows = kb.inline_keyboard
    assert rows[0][0].text == "✅ GigaChat 2 Lite"
    assert rows[1][0].text == "GigaChat 2 Pro"
    assert rows[2][0].text == "Закрыть"
    lite = ModelSelectionData.unpack(rows[0][0].callback_data or "")
    assert lite.model == "gigachat-2-lite"
    assert lite.display_name == "GigaChat 2 Lite"
    close = ModelSelectionData.unpack(rows[2][0].callback_data or "")
    assert close.model == CLOSE_MODEL
