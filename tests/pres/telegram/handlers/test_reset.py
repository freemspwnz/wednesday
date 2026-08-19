"""Tests for /reset command and reset confirmation callback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message

from app.dto import ChatContext
from presentation.aiogram.messages import image as image_msg
from presentation.aiogram.routers.image import ResetViewsData, cb_reset_views, cmd_reset

from ..factories import make_callback_query, make_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_reset_sends_confirmation_with_two_buttons(
    mock_scope: MagicMock,
) -> None:
    message = make_message(text="/reset")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await cmd_reset(message, mock_scope)

    answer.assert_awaited_once()
    assert answer.await_args is not None
    text = answer.await_args.args[0]
    assert text == image_msg.RESET_CONFIRM_PROMPT
    markup = answer.await_args.kwargs["reply_markup"]
    buttons = markup.inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[0].text == "Да"
    assert buttons[1].text == "Отмена"
    confirm_data = ResetViewsData.unpack(buttons[0].callback_data or "")
    cancel_data = ResetViewsData.unpack(buttons[1].callback_data or "")
    assert confirm_data.confirm is True
    assert cancel_data.confirm is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_reset_confirm_clears_views_and_edits_message(
    mock_scope: MagicMock,
    chat_context: ChatContext,
) -> None:
    mock_scope.image_catalog_uc.reset_views = AsyncMock(return_value=5)
    payload = ResetViewsData(confirm=True)
    callback = make_callback_query(data=payload.pack())

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as cb_answer,
        patch.object(Message, "edit_text", new_callable=AsyncMock) as edit_text,
    ):
        await cb_reset_views(callback, payload, chat_context, mock_scope)

    mock_scope.image_catalog_uc.reset_views.assert_awaited_once_with(chat_id=chat_context.id)
    edit_text.assert_awaited_once_with(image_msg.RESET_DONE.format(count=5))
    cb_answer.assert_awaited_once_with()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_reset_cancel_edits_message_without_clearing(
    mock_scope: MagicMock,
    chat_context: ChatContext,
) -> None:
    payload = ResetViewsData(confirm=False)
    callback = make_callback_query(data=payload.pack())

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as cb_answer,
        patch.object(Message, "edit_text", new_callable=AsyncMock) as edit_text,
    ):
        await cb_reset_views(callback, payload, chat_context, mock_scope)

    mock_scope.image_catalog_uc.reset_views.assert_not_awaited()
    edit_text.assert_awaited_once_with(image_msg.RESET_CANCELLED)
    cb_answer.assert_awaited_once_with()
