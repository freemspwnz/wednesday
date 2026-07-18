"""Shared fixtures for presentation telegram tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dto import ChatContext, UserContext
from domain.user import UserRole

from .factories import make_message, mk_chat_context, mk_user_context

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
    scope.models = AsyncMock()
    scope.image_commands_uc = AsyncMock()
    return scope


@pytest.fixture
def admin_user() -> UserContext:
    return mk_user_context(role=UserRole.ADMIN)


@pytest.fixture
def chat_context() -> ChatContext:
    return mk_chat_context()
