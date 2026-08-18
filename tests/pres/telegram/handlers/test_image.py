"""Tests for image router handlers (/random, /generate) and vote keyboard."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Chat as TgChat, Message, PhotoSize, User as TgUser

from app.dto import ChatContext, ImageCard, UserContext
from domain.catalog import Model
from domain.chat import ChatProfile, ChatType
from domain.image import (
    ImageMeta,
    ImageNotFoundError,
    ImagePrompts,
    ImageRender,
    NormalizedPrompt,
    PromptRejectedError,
    PromptSource,
    TelegramFileId,
)
from presentation.aiogram.messages import exceptions as exc_msg, image as image_msg
from presentation.aiogram.routers.image import (
    ImageVoteData,
    build_vote_kb,
    cb_image_vote,
    cmd_generate,
    cmd_random,
)
from tests.dom.image.factories import dt, mk_image, mk_rating

from ..factories import make_callback_query, make_message, mk_chat_context, mk_user_context

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)
_IMAGE_KEY = str(UUID(int=7))


@pytest.mark.unit
def test_build_vote_kb_shows_likes_and_dislikes() -> None:
    kb = build_vote_kb(image_id=_IMAGE_KEY, rating=mk_rating(likes=3, dislikes=1))
    row = kb.inline_keyboard[0]
    assert len(row) == 2
    assert row[0].text == "👍 3"
    assert row[1].text == "👎 1"

    up = ImageVoteData.unpack(row[0].callback_data or "")
    down = ImageVoteData.unpack(row[1].callback_data or "")
    assert up is not None and down is not None
    assert up.value == 1
    assert down.value == -1
    assert up.image_id == _IMAGE_KEY


def _mk_render() -> ImageRender:
    return ImageRender(
        content=b"png-bytes",
        prompts=ImagePrompts(
            primary=NormalizedPrompt.parse("frog"),
            source=PromptSource.USER,
        ),
    )


def _mk_sent_photo(*, file_id: str = "AgACAgIAAxkBAAI") -> Message:
    return Message(
        message_id=2,
        date=_MSG_DATE,
        chat=TgChat(id=1, type="private"),
        from_user=TgUser(id=1, is_bot=True, first_name="Bot"),
        photo=[
            PhotoSize(file_id=file_id, file_unique_id="uid", width=100, height=100),
        ],
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_generate_with_prompt_success(
    mock_scope: MagicMock,
    chat_context: ChatContext,
) -> None:
    user = mk_user_context()
    render = _mk_render()
    image = mk_image(
        image_id=11,
        rating=mk_rating(likes=1),
        created_at=dt(10),
        file_id=TelegramFileId.parse("AgACAgIAAxkBAAI"),
    )
    card = ImageCard.from_domain(image)

    mock_scope.user_generation_uc.assert_allowed = AsyncMock()
    mock_scope.image_generation_uc.by_user = AsyncMock(return_value=render)
    mock_scope.image_generation_uc.register = AsyncMock(return_value=card)
    mock_scope.user_generation_uc.record_usage = AsyncMock()

    message = make_message(text="/generate cute frog")
    command = CommandObject(prefix="/", command="generate", args="cute frog")
    status = MagicMock()
    status.delete = AsyncMock()
    sent = _mk_sent_photo()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock, return_value=status) as answer,
        patch.object(Message, "answer_photo", new_callable=AsyncMock, return_value=sent) as answer_photo,
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock) as edit_markup,
    ):
        await cmd_generate(message, command, user, chat_context, mock_scope)

    answer.assert_awaited_once_with(image_msg.GENERATION_STARTED)
    mock_scope.user_generation_uc.assert_allowed.assert_awaited_once()
    mock_scope.image_generation_uc.by_user.assert_awaited_once()
    by_user_kwargs = mock_scope.image_generation_uc.by_user.await_args.kwargs
    assert by_user_kwargs["prompt"] == "cute frog"
    mock_scope.image_generation_uc.random.assert_not_called()
    answer_photo.assert_awaited_once()
    mock_scope.image_generation_uc.register.assert_awaited_once()
    kwargs = mock_scope.image_generation_uc.register.await_args.kwargs
    assert kwargs["file_id"] == TelegramFileId.parse("AgACAgIAAxkBAAI")
    assert isinstance(kwargs["meta"], ImageMeta)
    assert kwargs["meta"].author_id == user.id
    assert kwargs["meta"].model == Model.parse(user.model)
    assert kwargs["chat_id"] == chat_context.id
    assert "image_id" in kwargs
    edit_markup.assert_awaited_once()
    assert edit_markup.await_args is not None
    markup = edit_markup.await_args.kwargs["reply_markup"]
    assert [b.text for b in markup.inline_keyboard[0]] == ["👍 1", "👎 0"]
    mock_scope.user_generation_uc.record_usage.assert_awaited_once()
    status.delete.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_generate_without_args_uses_random(
    mock_scope: MagicMock,
    chat_context: ChatContext,
) -> None:
    user = mk_user_context()
    render = _mk_render()
    image = mk_image(image_id=12, rating=mk_rating(likes=1), created_at=dt(10))
    card = ImageCard.from_domain(image)

    mock_scope.user_generation_uc.assert_allowed = AsyncMock()
    mock_scope.image_generation_uc.random = AsyncMock(return_value=render)
    mock_scope.image_generation_uc.register = AsyncMock(return_value=card)
    mock_scope.user_generation_uc.record_usage = AsyncMock()

    message = make_message(text="/generate")
    command = CommandObject(prefix="/", command="generate", args=None)
    status = MagicMock()
    status.delete = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock, return_value=status),
        patch.object(Message, "answer_photo", new_callable=AsyncMock, return_value=_mk_sent_photo()),
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock),
    ):
        await cmd_generate(message, command, user, chat_context, mock_scope)

    mock_scope.image_generation_uc.random.assert_awaited_once()
    mock_scope.image_generation_uc.by_user.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_generate_rejected_prompt_assigns_ban(
    mock_scope: MagicMock,
    chat_context: ChatContext,
) -> None:
    user = mk_user_context()
    mock_scope.user_generation_uc.assert_allowed = AsyncMock()
    mock_scope.image_generation_uc.by_user = AsyncMock(
        side_effect=PromptRejectedError("prohibited_content"),
    )
    mock_scope.user_moderation_uc.assign_ban = AsyncMock()
    mock_scope.user_generation_uc.record_usage = AsyncMock()

    message = make_message(text="/generate naked frog")
    command = CommandObject(prefix="/", command="generate", args="naked frog")
    status = MagicMock()
    status.delete = AsyncMock()
    status.edit_text = AsyncMock()

    with patch.object(Message, "answer", new_callable=AsyncMock, return_value=status) as answer:
        await cmd_generate(message, command, user, chat_context, mock_scope)

    mock_scope.logger.warning.assert_called_once_with(
        "Prompt rejected",
        user_id=str(user.id.value),
        code="prohibited_content",
    )
    mock_scope.user_generation_uc.assert_allowed.assert_awaited_once()
    mock_scope.image_generation_uc.by_user.assert_awaited_once()
    mock_scope.user_moderation_uc.assign_ban.assert_awaited_once()
    mock_scope.user_generation_uc.record_usage.assert_not_awaited()
    answer.assert_awaited_once_with(image_msg.GENERATION_STARTED)
    status.edit_text.assert_awaited_once_with(exc_msg.PROMPT_REJECTED)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_random_empty_catalog(
    chat_context: ChatContext,
    mock_scope: MagicMock,
) -> None:
    mock_scope.image_catalog_uc.pick_for_chat = AsyncMock(return_value=None)
    message = make_message(text="/random")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await cmd_random(message, chat_context, mock_scope)

    answer.assert_awaited_once_with(image_msg.RANDOM_CATALOG_EMPTY)
    mock_scope.image_catalog_uc.mark_shown.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_random_sends_photo_with_keyboard(
    chat_context: ChatContext,
    mock_scope: MagicMock,
) -> None:
    image = mk_image(
        image_id=7,
        rating=mk_rating(likes=2, dislikes=1),
        created_at=dt(10),
        file_id=TelegramFileId.parse("AgACAgIAAxkB"),
    )
    card = ImageCard.from_domain(image)
    mock_scope.image_catalog_uc.pick_for_chat = AsyncMock(return_value=card)
    message = make_message(text="/random")

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "answer_photo", new_callable=AsyncMock) as answer_photo,
    ):
        await cmd_random(message, chat_context, mock_scope)

    answer.assert_not_awaited()
    answer_photo.assert_awaited_once()
    kwargs = answer_photo.await_args_list[0].kwargs
    assert kwargs["photo"] == "AgACAgIAAxkB"
    markup = kwargs["reply_markup"]
    assert markup is not None
    assert [b.text for b in markup.inline_keyboard[0]] == ["👍 2", "👎 1"]
    mock_scope.image_catalog_uc.mark_shown.assert_awaited_once()
    mark_kwargs = mock_scope.image_catalog_uc.mark_shown.await_args.kwargs
    assert mark_kwargs["chat_id"] == chat_context.id
    assert mark_kwargs["image_id"] == card.id


@pytest.fixture
def voter_context() -> UserContext:
    return mk_user_context()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_image_vote_updates_markup(
    voter_context: UserContext,
    mock_scope: MagicMock,
) -> None:
    image = mk_image(image_id=9, rating=mk_rating(likes=4, dislikes=1), created_at=dt(10))
    card = ImageCard.from_domain(image)
    private_chat = mk_chat_context(tg_id=voter_context.tg_id, chat_type=ChatType.PRIVATE, domain_id=77)
    mock_scope.chat_management_uc.register = AsyncMock(return_value=private_chat)
    mock_scope.image_vote_uc.vote = AsyncMock(return_value=card)
    payload = ImageVoteData(image_id=str(UUID(int=9)), value=1)
    callback = make_callback_query(data=payload.pack(), chat_id=-100)

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock) as edit_markup,
    ):
        await cb_image_vote(callback, payload, voter_context, mock_scope)

    mock_scope.chat_management_uc.register.assert_awaited_once_with(
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=voter_context.tg_id),
    )
    mock_scope.image_vote_uc.vote.assert_awaited_once()
    vote_kwargs = mock_scope.image_vote_uc.vote.await_args.kwargs
    assert vote_kwargs["voter_id"] == voter_context.id
    assert vote_kwargs["chat_id"] == private_chat.id
    edit_markup.assert_awaited_once()
    assert edit_markup.await_args is not None
    markup = edit_markup.await_args.kwargs["reply_markup"]
    assert [b.text for b in markup.inline_keyboard[0]] == ["👍 4", "👎 1"]
    answer.assert_awaited_once_with()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_image_vote_same_markup_skips_edit(
    voter_context: UserContext,
    mock_scope: MagicMock,
) -> None:
    image = mk_image(image_id=9, rating=mk_rating(likes=4, dislikes=1), created_at=dt(10))
    card = ImageCard.from_domain(image)
    mock_scope.image_vote_uc.vote = AsyncMock(return_value=card)
    payload = ImageVoteData(image_id=str(UUID(int=9)), value=1)
    callback = make_callback_query(data=payload.pack(), chat_id=1)
    assert isinstance(callback.message, Message)
    object.__setattr__(
        callback.message,
        "reply_markup",
        build_vote_kb(image_id=str(UUID(int=9)), rating=card.rating),
    )

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock) as edit_markup,
    ):
        await cb_image_vote(callback, payload, voter_context, mock_scope)

    edit_markup.assert_not_awaited()
    answer.assert_awaited_once_with()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_image_vote_noop_answers_without_edit(
    voter_context: UserContext,
    mock_scope: MagicMock,
) -> None:
    mock_scope.image_vote_uc.vote = AsyncMock(return_value=None)
    payload = ImageVoteData(image_id=str(UUID(int=9)), value=1)
    callback = make_callback_query(data=payload.pack(), chat_id=1)

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock) as edit_markup,
    ):
        await cb_image_vote(callback, payload, voter_context, mock_scope)

    edit_markup.assert_not_awaited()
    answer.assert_awaited_once_with()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_image_vote_image_not_found(
    voter_context: UserContext,
    mock_scope: MagicMock,
) -> None:
    mock_scope.image_vote_uc.vote = AsyncMock(side_effect=ImageNotFoundError(str(UUID(int=404))))
    payload = ImageVoteData(image_id=str(UUID(int=404)), value=-1)
    callback = make_callback_query(data=payload.pack())

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as callback_answer,
    ):
        await cb_image_vote(callback, payload, voter_context, mock_scope)

    callback_answer.assert_awaited_once_with(exc_msg.IMAGE_NOT_FOUND, show_alert=True)
