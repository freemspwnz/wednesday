"""Tests for user router handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Message

from app.dto import UserContext
from domain.catalog import SubscriptionTier
from domain.kernel.vo import NonEmptyStr
from domain.user import UserRole
from presentation.aiogram.messages import profile as profile_msg
from presentation.aiogram.routers import user as handlers

from ..helpers import make_message


@pytest.fixture
def user_context() -> UserContext:
    return UserContext(
        tg_id=1,
        is_bot=False,
        first_name=NonEmptyStr("U"),
        role=UserRole.USER,
        subscription_tier=SubscriptionTier.FREE,
        subscription_daily_limit=3,
        subscription_cooldown_minutes=5,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_me_replies_with_profile(user_context: UserContext) -> None:
    message = make_message(text="/me")
    expected = profile_msg.format_me(user_context)
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_me(message, user_context)
    answer.assert_awaited_once_with(text=expected)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_me_role_unknown(user_context: UserContext) -> None:
    user_context.role = None
    message = make_message(text="/me")
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_me(message, user_context)
    answer.assert_awaited_once_with(text=profile_msg.ROLE_UNKNOWN)
