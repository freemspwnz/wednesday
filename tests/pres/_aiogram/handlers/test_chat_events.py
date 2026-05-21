"""Tests for chat event handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import Chat, ChatMember, ChatMemberBanned, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated, User

from domain.kernel.exceptions import InvalidStateTransitionError
from presentation.aiogram.routers import chat_event as h

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def _event(
    *,
    status: ChatMemberStatus,
    is_bot: bool = False,
    chat_type: str = "supergroup",
) -> ChatMemberUpdated:
    member_user = User(id=1 if is_bot else 5, is_bot=is_bot, first_name="U")
    new_member: ChatMember
    if status == ChatMemberStatus.MEMBER:
        new_member = ChatMemberMember(user=member_user, status=ChatMemberStatus.MEMBER)
    elif status == ChatMemberStatus.LEFT:
        new_member = ChatMemberLeft(user=member_user, status=ChatMemberStatus.LEFT)
    else:
        new_member = ChatMemberBanned(
            user=member_user, status=ChatMemberStatus.KICKED, until_date=datetime(1970, 1, 1, tzinfo=UTC)
        )
    return ChatMemberUpdated(
        chat=Chat(id=-100, type=chat_type),
        from_user=User(id=99, is_bot=False, first_name="Admin"),
        date=_MSG_DATE,
        old_chat_member=ChatMemberMember(user=member_user, status=ChatMemberStatus.MEMBER),
        new_chat_member=new_member,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_left_deactivates(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: object,
) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    await h.on_my_chat_member(_event(status=ChatMemberStatus.LEFT, is_bot=True), AsyncMock(), mock_logger, mock_scope)
    mock_scope.chat_commands_uc.deactivate.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_invalid_transition(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: object,
) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    mock_scope.chat_commands_uc.deactivate.side_effect = InvalidStateTransitionError("already")
    await h.on_my_chat_member(_event(status=ChatMemberStatus.LEFT, is_bot=True), AsyncMock(), mock_logger, mock_scope)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_joined_sends_welcome(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    await h.on_my_chat_member(_event(status=ChatMemberStatus.MEMBER, is_bot=True), bot, mock_logger, MagicMock())
    bot.send_message.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chat_member_messages(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    await h.on_chat_member(_event(status=ChatMemberStatus.MEMBER), bot, mock_logger)
    await h.on_chat_member(_event(status=ChatMemberStatus.LEFT), bot, mock_logger)
    assert bot.send_message.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_forbidden_send_logged(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=TelegramForbiddenError(method=MagicMock(), message="no"))
    await h.on_my_chat_member(_event(status=ChatMemberStatus.MEMBER, is_bot=True), bot, mock_logger, MagicMock())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chat_member_skips_greetings_in_private(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    await h.on_chat_member(_event(status=ChatMemberStatus.MEMBER, chat_type="private"), bot, mock_logger)

    bot.send_message.assert_not_awaited()
