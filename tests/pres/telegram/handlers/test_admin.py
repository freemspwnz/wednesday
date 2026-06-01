"""Direct tests for admin router handlers."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from app.dto import ChatContext, UserContext
from domain.kernel.exceptions import InvalidStateTransitionError
from presentation.aiogram.messages import admin as admin_msg, commands as cmd_msg, exceptions as exc_msg
from presentation.aiogram.routers import admin as h

from ..factories import make_message, mk_user_context


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (h.cmd_status, cmd_msg.WIP),
        (h.cmd_activate_usage, admin_msg.ACTIVATE_USAGE),
        (h.cmd_unban_usage, admin_msg.UNBAN_USAGE),
    ],
)
async def test_simple_replies(handler: object, expected: str) -> None:
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handler(make_message())  # type: ignore[operator]
    answer.assert_awaited_once_with(expected)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_chat_not_found(mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = None
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_activate_chat(make_message(), ["-1001"], AsyncMock(), mock_logger, mock_scope)
    answer.assert_awaited_once_with(exc_msg.CHAT_NOT_FOUND)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_success(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: ChatContext,
) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.admin.is_bot_member_of_chat",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        await h.cmd_activate_chat(make_message(), ["-1001"], AsyncMock(), mock_logger, mock_scope)

    mock_scope.chat_commands_uc.activate.assert_awaited_once()
    answer.assert_awaited_once_with(admin_msg.CHAT_ACTIVATED.format(tg_chat_id=-1001))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_bot_absent_deactivates_active_chat(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: ChatContext,
) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.admin.is_bot_member_of_chat",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await h.cmd_activate_chat(make_message(), ["-1001"], AsyncMock(), mock_logger, mock_scope)

    mock_scope.chat_commands_uc.deactivate.assert_awaited_once()
    answer.assert_awaited_once_with(admin_msg.CHAT_DEACTIVATED_BOT_ABSENT.format(tg_chat_id=-1001))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_bot_absent_already_inactive_on_deactivate(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: ChatContext,
) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    mock_scope.chat_commands_uc.deactivate.side_effect = InvalidStateTransitionError("already")
    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.admin.is_bot_member_of_chat",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await h.cmd_activate_chat(make_message(), ["-1001"], AsyncMock(), mock_logger, mock_scope)

    answer.assert_awaited_once_with(
        admin_msg.BOT_NOT_IN_CHAT_ALREADY_INACTIVE.format(tg_chat_id=-1001),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_bot_absent_inactive_chat(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: ChatContext,
) -> None:
    inactive = replace(chat_context, is_active=False)
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = inactive
    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.admin.is_bot_member_of_chat",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await h.cmd_activate_chat(make_message(), ["-1001"], AsyncMock(), mock_logger, mock_scope)

    mock_scope.chat_commands_uc.deactivate.assert_not_awaited()
    answer.assert_awaited_once_with(admin_msg.BOT_NOT_IN_CHAT)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deactivate_success(mock_scope: MagicMock, mock_logger: MagicMock, chat_context: ChatContext) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_deactivate_chat(make_message(), ["-1001"], mock_logger, mock_scope)
    mock_scope.chat_commands_uc.deactivate.assert_awaited_once()
    answer.assert_awaited_once_with(admin_msg.CHAT_DEACTIVATED.format(tg_chat_id=-1001))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ban_success(mock_scope: MagicMock, mock_logger: MagicMock, admin_user: UserContext) -> None:
    target = mk_user_context(user_id=2)
    target.tg_id = 42
    mock_scope.registration_uc.find_user_by_tg_id.return_value = target
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_ban(make_message(), ["42", "7"], mock_logger, mock_scope, admin_user)
    mock_scope.user_commands_uc.ban.assert_awaited_once()
    answer.assert_awaited_once_with(admin_msg.USER_BANNED.format(tg_id=42, days=7))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mod_denied_by_domain_policy(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    admin_user: UserContext,
) -> None:
    from domain.user.exceptions import AccessDeniedError

    target = mk_user_context(user_id=2)
    target.tg_id = 42
    mock_scope.registration_uc.find_user_by_tg_id.return_value = target
    mock_scope.user_commands_uc.change_role.side_effect = AccessDeniedError("access_denied")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_mod(make_message(user_id=2), ["42"], mock_logger, mock_scope, admin_user)

    answer.assert_awaited_once_with(exc_msg.INSUFFICIENT_PERMISSIONS)
