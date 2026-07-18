"""Tests for image router handlers (/random, /generate) and vote keyboard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from aiogram.types import CallbackQuery, Message

from app.dto import ChatContext, ImageCard, UserContext
from domain.image import ImageId, ImageNotFoundError, TelegramFileId
from presentation.aiogram.messages import commands as cmd_msg, exceptions as exc_msg
from presentation.aiogram.routers.image import ImageVoteData, build_vote_kb
from presentation.aiogram.routers.image.router import cb_image_vote, cmd_generate, cmd_random
from tests.dom.image.factories import dt, mk_image

from ..factories import make_callback_query, make_message, mk_user_context


@pytest.mark.unit
def test_build_vote_kb_contains_up_and_down() -> None:
    kb = build_vote_kb(image_id=ImageId(UUID(int=7)))
    row = kb.inline_keyboard[0]
    assert len(row) == 2
    up_raw = row[0].callback_data
    assert up_raw is not None
    up = ImageVoteData.unpack(up_raw)
    down_raw = row[1].callback_data
    assert down_raw is not None
    down = ImageVoteData.unpack(down_raw)
    assert up is not None and down is not None
    assert up.value == 1
    assert down.value == -1
    assert up.image_id == str(UUID(int=7))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_generate_replies_wip() -> None:
    message = make_message(text="/generate")
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await cmd_generate(message)
    answer.assert_awaited_once_with(text=cmd_msg.WIP)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_random_empty_catalog(
    chat_context: ChatContext,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_scope.image_commands_uc.pick_for_chat = AsyncMock(return_value=None)
    message = make_message(text="/random")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await cmd_random(message, chat_context, mock_scope, mock_logger)

    answer.assert_awaited_once_with(cmd_msg.RANDOM_CATALOG_EMPTY)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_random_sends_photo_with_keyboard(
    chat_context: ChatContext,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    image = mk_image(
        image_id=7,
        score=2,
        created_at=dt(10),
        file_id=TelegramFileId.parse("AgACAgIAAxkB"),
    )
    card = ImageCard.from_domain(image)
    mock_scope.image_commands_uc.pick_for_chat = AsyncMock(return_value=card)
    message = make_message(text="/random")

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "answer_photo", new_callable=AsyncMock) as answer_photo,
    ):
        await cmd_random(message, chat_context, mock_scope, mock_logger)

    answer.assert_not_awaited()
    answer_photo.assert_awaited_once()
    kwargs = answer_photo.await_args_list[0].kwargs
    assert kwargs["photo"] == "AgACAgIAAxkB"
    assert kwargs["reply_markup"] is not None


@pytest.fixture
def voter_context() -> UserContext:
    return mk_user_context()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_image_vote_success(
    voter_context: UserContext,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    image = mk_image(image_id=9, score=1, created_at=dt(10))
    mock_scope.image_commands_uc.vote = AsyncMock(return_value=image)
    payload = ImageVoteData(image_id=str(UUID(int=9)), value=1)
    callback = make_callback_query(data=payload.pack())

    with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer:
        await cb_image_vote(callback, payload, voter_context, mock_scope, mock_logger)

    mock_scope.image_commands_uc.vote.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_image_vote_image_not_found(
    voter_context: UserContext,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_scope.image_commands_uc.vote = AsyncMock(side_effect=ImageNotFoundError(str(UUID(int=404))))
    payload = ImageVoteData(image_id=str(UUID(int=404)), value=-1)
    callback = make_callback_query(data=payload.pack())

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as callback_answer,
    ):
        await cb_image_vote(callback, payload, voter_context, mock_scope, mock_logger)

    callback_answer.assert_awaited_once_with(exc_msg.IMAGE_NOT_FOUND, show_alert=True)
