"""Direct tests for admin router handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from app.dto import UserContext
from domain.user.exceptions import AccessDeniedError
from presentation.aiogram.messages import admin as admin_msg, commands as cmd_msg, exceptions as exc_msg
from presentation.aiogram.routers import admin as h

from ..factories import make_message, mk_user_context


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (h.cmd_status, cmd_msg.WIP),
        (h.cmd_unban_usage, admin_msg.UNBAN_USAGE),
    ],
)
async def test_simple_replies(handler: object, expected: str) -> None:
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handler(make_message())  # type: ignore[operator]
    answer.assert_awaited_once_with(expected)


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
    target = mk_user_context(user_id=2)
    target.tg_id = 42
    mock_scope.registration_uc.find_user_by_tg_id.return_value = target
    mock_scope.user_commands_uc.change_role.side_effect = AccessDeniedError("access_denied")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_mod(make_message(user_id=2), ["42"], mock_logger, mock_scope, admin_user)

    answer.assert_awaited_once_with(exc_msg.INSUFFICIENT_PERMISSIONS)
