"""Tests for RegistrationMiddleware."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
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
from domain.kernel.vo import NonEmptyStr
from domain.user import UserProfile
from presentation.aiogram.middlewares.update.registration import RegistrationMiddleware

from ..factories import mk_chat_context, mk_user_context

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.unit
class TestMapping:
    def test_to_user_profile(self) -> None:
        tg_user = User(
            id=42,
            is_bot=False,
            first_name="Ada",
            last_name="Lovelace",
            username="ada",
            language_code="en",
            is_premium=True,
        )
        profile = RegistrationMiddleware._to_user_profile(tg_user)
        assert profile == UserProfile(
            telegram_id=42,
            is_bot=False,
            first_name=NonEmptyStr("Ada"),
            last_name=NonEmptyStr("Lovelace"),
            username="ada",
            language_code="en",
            has_tg_premium=True,
        )

    def test_to_chat_profile(self) -> None:
        profile = RegistrationMiddleware._to_chat_profile(Chat(id=-1001, type="supergroup", title="Ops"))
        assert profile.telegram_id == -1001
        assert profile.type == ChatType.SUPERGROUP
        assert profile.title == "Ops"

    @pytest.mark.parametrize(
        ("entity_type", "event_factory"),
        [
            (
                "user",
                lambda: Message(
                    message_id=1,
                    date=_MSG_DATE,
                    chat=Chat(id=1, type="private"),
                    from_user=User(id=1, is_bot=False, first_name="A"),
                ),
            ),
            (
                "chat",
                lambda: Message(
                    message_id=1,
                    date=_MSG_DATE,
                    chat=Chat(id=-99, type="group"),
                    from_user=User(id=1, is_bot=False, first_name="A"),
                ),
            ),
        ],
    )
    def test_extract_from_message(
        self, entity_type: Literal["user", "chat"], event_factory: Callable[[], Message]
    ) -> None:
        event = event_factory()
        attr = "from_user" if entity_type == "user" else "chat"
        found = RegistrationMiddleware._extract_entity(entity_type=entity_type, event=event)
        assert found is getattr(event, attr)

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
        assert RegistrationMiddleware._extract_entity(entity_type="user", event=callback) is user
        assert RegistrationMiddleware._extract_entity(entity_type="chat", event=callback) is chat

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
    call_kwargs = mock_scope.user_lifecycle_uc.register.await_args.kwargs
    assert call_kwargs["profile"].telegram_id == 1


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
    assert call_kwargs["profile"].telegram_id == 1


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
