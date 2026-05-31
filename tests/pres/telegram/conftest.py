"""Shared fixtures for presentation telegram tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.dto import ChatContext, UserContext
from domain.chat import ChatId, ChatType
from domain.kernel.vo import NonEmptyStr
from domain.user import UserRole

from .helpers import make_message

__all__ = ["make_message"]


@pytest.fixture
def mock_logger() -> MagicMock:
    logger = MagicMock()
    logger.bind.return_value = logger
    return logger


@pytest.fixture
def mock_rate_limiter() -> MagicMock:
    limiter = MagicMock()
    limiter.limits = {
        "global": MagicMock(),
        "chat": MagicMock(),
        "user": MagicMock(),
        "throttling": MagicMock(),
    }
    limiter.call = AsyncMock()
    return limiter


@pytest.fixture
def mock_scope(mock_logger: MagicMock) -> MagicMock:
    scope = MagicMock()
    scope.logger = mock_logger
    scope.registration_uc = AsyncMock()
    scope.user_commands_uc = AsyncMock()
    scope.chat_commands_uc = AsyncMock()
    return scope


@pytest.fixture
def admin_user() -> UserContext:
    return UserContext(
        tg_id=1,
        is_bot=False,
        first_name=NonEmptyStr("Admin"),
        role=UserRole.ADMIN,
    )


@pytest.fixture
def chat_context() -> ChatContext:
    return ChatContext(
        tg_id=-1001,
        type=ChatType.SUPERGROUP,
        id=ChatId(value=UUID(int=10)),
    )
