"""Тесты AdminAccessMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from app.dto import UserContext
from domain.kernel.vo import NonEmptyStr
from domain.user import UserRole
from presentation.aiogram.messages import access as access_msg
from presentation.aiogram.middlewares.router.admin_access import AdminAccessMiddleware


def _user(*, tg_id: int, role: UserRole | None = UserRole.USER) -> UserContext:
    return UserContext(
        tg_id=tg_id,
        is_bot=False,
        first_name=NonEmptyStr("Test"),
        role=role,
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_admin_id", "user", "expect_handler"),
    [
        (1, _user(tg_id=42), False),
        (1, _user(tg_id=1), True),
        (999, _user(tg_id=42, role=UserRole.ADMIN), True),
    ],
)
async def test_access(
    config_admin_id: int,
    user: UserContext,
    expect_handler: bool,
) -> None:
    logger = MagicMock()
    logger.bind.return_value = logger
    middleware = AdminAccessMiddleware(admin_id=config_admin_id, logger=logger)
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()
    handler = AsyncMock()
    data: dict[str, object] = {"user": user}

    result = await middleware(handler, message, data)

    if expect_handler:
        handler.assert_awaited_once()
        assert "admin_id" not in data
    else:
        assert result is None
        handler.assert_not_awaited()
        message.answer.assert_awaited_once_with(access_msg.ADMIN_DENIED)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_user_returns_none() -> None:
    logger = MagicMock()
    logger.bind.return_value = logger
    middleware = AdminAccessMiddleware(admin_id=1, logger=logger)
    handler = AsyncMock()

    result = await middleware(handler, MagicMock(spec=Message), {})

    assert result is None
    handler.assert_not_awaited()
