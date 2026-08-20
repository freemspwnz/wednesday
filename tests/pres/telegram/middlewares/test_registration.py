"""Tests for RegistrationMiddleware."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMember,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    Update,
    User,
)

from domain.chat import ChatType
from presentation.aiogram.middlewares.update.registration import RegistrationMiddleware

from ..factories import mk_chat_context, mk_user_context

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.unit
class TestMapping:
    def test_extract_user_from_message(self) -> None:
        user = User(id=42, is_bot=False, first_name="Ada")
        message = Message(
            message_id=1,
            date=_MSG_DATE,
            chat=Chat(id=1, type="private"),
            from_user=user,
        )
        assert RegistrationMiddleware._extract_user(message) is user

    def test_extract_chat_from_message(self) -> None:
        chat = Chat(id=-99, type="group")
        message = Message(
            message_id=1,
            date=_MSG_DATE,
            chat=chat,
            from_user=User(id=1, is_bot=False, first_name="A"),
        )
        assert RegistrationMiddleware._extract_chat(message) is chat

    def test_extract_at_from_message(self) -> None:
        message = Message(
            message_id=1,
            date=_MSG_DATE,
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="A"),
        )
        assert RegistrationMiddleware._extract_at(message) == _MSG_DATE

    def test_unwrap_update_prefers_callback_query(self) -> None:
        user = User(id=7, is_bot=False, first_name="Voter")
        chat = Chat(id=1, type="private")
        message = Message(message_id=1, date=_MSG_DATE, chat=chat, from_user=user)
        callback = CallbackQuery(
            id="cq1",
            from_user=user,
            chat_instance="test",
            data="imgvote:x:1",
            message=message,
        )
        update = Update(update_id=1, callback_query=callback)

        assert RegistrationMiddleware._unwrap_update(update) is callback
        assert RegistrationMiddleware._extract_user(callback) is user
        assert RegistrationMiddleware._extract_chat(callback) is chat

    @pytest.mark.parametrize(
        ("joined", "expected_skip"),
        [
            (False, True),
            (True, False),
        ],
    )
    def test_should_skip_registration(self, joined: bool, expected_skip: bool) -> None:
        assert RegistrationMiddleware._should_skip_registration(_bot_left_event(joined=joined)) is expected_skip


def _bot_left_event(*, joined: bool = False) -> ChatMemberUpdated:
    bot = User(id=1, is_bot=True, first_name="Bot")
    old_member: ChatMember
    new_member: ChatMember
    if joined:
        old_member = ChatMemberLeft(user=bot, status=ChatMemberStatus.LEFT)
        new_member = ChatMemberMember(user=bot, status=ChatMemberStatus.MEMBER)
    else:
        old_member = ChatMemberMember(user=bot, status=ChatMemberStatus.MEMBER)
        new_member = ChatMemberLeft(user=bot, status=ChatMemberStatus.LEFT)
    return ChatMemberUpdated(
        chat=Chat(id=-100, type="supergroup"),
        from_user=User(id=99, is_bot=False, first_name="Admin"),
        date=_MSG_DATE,
        old_chat_member=old_member,
        new_chat_member=new_member,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_registers_user_and_chat(mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    reg_user = mk_user_context()
    reg_chat = mk_chat_context(tg_id=1, chat_type=ChatType.PRIVATE)
    mock_scope.user_lifecycle_uc.register.return_value = reg_user
    mock_scope.chat_management_uc.register.return_value = reg_chat

    middleware = RegistrationMiddleware(logger=mock_logger)
    handler = AsyncMock()
    message = Message(
        message_id=1,
        date=_MSG_DATE,
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="A"),
    )
    data: dict[str, object] = {"scope": mock_scope}

    await middleware(handler, message, data)

    assert data["user"] == reg_user
    assert data["chat"] == reg_chat
    handler.assert_awaited_once()
    mock_scope.user_lifecycle_uc.register.assert_awaited_once()
    user_kwargs = mock_scope.user_lifecycle_uc.register.await_args.kwargs
    assert user_kwargs["tg_id"] == 1
    assert user_kwargs["at"] == _MSG_DATE
    mock_scope.chat_management_uc.register.assert_awaited_once()
    chat_kwargs = mock_scope.chat_management_uc.register.await_args.kwargs
    assert chat_kwargs["tg_id"] == 1
    assert chat_kwargs["type"] == "private"
    assert chat_kwargs["at"] == _MSG_DATE


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_skips_on_bot_left(mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    middleware = RegistrationMiddleware(logger=mock_logger)
    handler = AsyncMock()
    data: dict[str, object] = {"scope": mock_scope}

    await middleware(handler, _bot_left_event(), data)

    assert data["user"] is None
    assert data["chat"] is None
    mock_scope.user_lifecycle_uc.register.assert_not_awaited()
    mock_scope.chat_management_uc.register.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_registers_user_from_callback_query_update(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    reg_user = mk_user_context()
    reg_chat = mk_chat_context(tg_id=1, chat_type=ChatType.PRIVATE)
    mock_scope.user_lifecycle_uc.register.return_value = reg_user
    mock_scope.chat_management_uc.register.return_value = reg_chat

    middleware = RegistrationMiddleware(logger=mock_logger)
    handler = AsyncMock()
    user = User(id=1, is_bot=False, first_name="A")
    chat = Chat(id=1, type="private")
    message = Message(message_id=1, date=_MSG_DATE, chat=chat, from_user=user)
    callback = CallbackQuery(
        id="cq1",
        from_user=user,
        chat_instance="test",
        data="imgvote:x:-1",
        message=message,
    )
    update = Update(update_id=42, callback_query=callback)
    data: dict[str, object] = {"scope": mock_scope}

    await middleware(handler, update, data)

    assert data["user"] == reg_user
    assert data["chat"] == reg_chat
    handler.assert_awaited_once()
    mock_scope.user_lifecycle_uc.register.assert_awaited_once()
    call_kwargs = mock_scope.user_lifecycle_uc.register.await_args.kwargs
    assert call_kwargs["tg_id"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_call_raises_without_scope(mock_logger: MagicMock) -> None:
    middleware = RegistrationMiddleware(logger=mock_logger)
    message = Message(
        message_id=1,
        date=_MSG_DATE,
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="A"),
    )

    with pytest.raises(RuntimeError, match="Request scope is missing"):
        await middleware(AsyncMock(), message, {})
