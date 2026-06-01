"""Tests for presentation setup helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramAPIError

import presentation.aiogram.setup as setup_mod
from presentation.aiogram.filters.access import AdminAccessFilter
from presentation.aiogram.routers.admin import admin_router
from presentation.aiogram.setup import build_root_router, setup_bot, setup_dp, setup_routers


@pytest.mark.unit
def test_build_root_router_includes_routers(monkeypatch: pytest.MonkeyPatch) -> None:
    children = [Router(name=n) for n in ("admin", "chat_event", "image", "user", "common")]
    monkeypatch.setattr(setup_mod, "admin_router", children[0])
    monkeypatch.setattr(setup_mod, "chat_event_router", children[1])
    monkeypatch.setattr(setup_mod, "image_router", children[2])
    monkeypatch.setattr(setup_mod, "user_router", children[3])
    monkeypatch.setattr(setup_mod, "common_router", children[4])

    root = build_root_router()

    assert root.name == "root"
    assert len(root.sub_routers) == 5


@pytest.mark.unit
def test_setup_bot_registers_session_middleware(mock_logger: MagicMock, mock_rate_limiter: MagicMock) -> None:
    bot = MagicMock(spec=Bot)
    bot.session = MagicMock()
    bot.session.middleware = MagicMock()
    retrier = MagicMock()

    setup_bot(bot=bot, rate_limiter=mock_rate_limiter, retrier=retrier, logger=mock_logger)

    assert bot.session.middleware.call_count == 2


@pytest.mark.unit
def test_setup_routers_attaches_admin_access_filter(mock_logger: MagicMock) -> None:
    setup_routers(logger=mock_logger)

    root_filters = admin_router.message._handler.filters
    assert root_filters is not None
    assert any(isinstance(fo.callback, AdminAccessFilter) for fo in root_filters)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_dp_registers_handlers_and_middleware(mock_logger: MagicMock, mock_rate_limiter: MagicMock) -> None:
    dp = Dispatcher()
    scope_factory = MagicMock()

    with patch.object(setup_mod, "build_root_router", return_value=Router(name="root")):
        setup_dp(
            dp=dp,
            scope_factory=scope_factory,
            rate_limiter=mock_rate_limiter,
            admin_id=1,
            logger=mock_logger,
        )

    assert dp.startup.handlers
    assert dp.shutdown.handlers


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dp_startup_handles_telegram_errors(mock_logger: MagicMock) -> None:
    dp = Dispatcher()
    bot = AsyncMock(spec=Bot)
    bot.set_my_commands = AsyncMock(side_effect=TelegramAPIError(method=MagicMock(), message="fail"))
    bot.send_message = AsyncMock(side_effect=TelegramAPIError(method=MagicMock(), message="fail"))

    with patch.object(setup_mod, "build_root_router", return_value=Router(name="root")):
        setup_dp(dp=dp, scope_factory=MagicMock(), rate_limiter=MagicMock(), admin_id=1, logger=mock_logger)

    for handler in dp.startup.handlers:
        await handler.callback(bot)
