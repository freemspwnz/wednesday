"""Тесты точки входа wednesday/main.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from main import main

from app.exceptions import PrometheusHttpExporterError


@pytest.fixture
def main_mocks() -> dict[str, MagicMock | AsyncMock]:
    config = MagicMock()
    config.telegram.token.get_secret_value.return_value = "test-token"
    config.telegram.admin_id = 1
    config.telegram.rate_limit = MagicMock()
    config.telegram.retry = MagicMock()

    container = MagicMock()
    container.observe.logger.bind.return_value = MagicMock()
    container.observe.collector = MagicMock()
    container.observe.collector.serve = MagicMock()
    container.shutdown = AsyncMock()
    container.get_scope = MagicMock()
    container.resilience.rate_limiter.return_value = MagicMock()
    container.resilience.retry.return_value = MagicMock()

    bot = MagicMock()
    bot.session.close = AsyncMock()

    dp = MagicMock()
    dp.start_polling = AsyncMock()

    return {
        "config": config,
        "container": container,
        "bot": bot,
        "dp": dp,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_closes_bot_and_shuts_down_container(main_mocks: dict[str, MagicMock | AsyncMock]) -> None:
    with (
        patch("main.Config", return_value=main_mocks["config"]),
        patch("main.Container", return_value=main_mocks["container"]),
        patch("main.Bot", return_value=main_mocks["bot"]),
        patch("main.Dispatcher", return_value=main_mocks["dp"]),
        patch("main.setup_bot"),
        patch("main.setup_dp"),
    ):
        await main()

    main_mocks["bot"].session.close.assert_awaited_once()
    main_mocks["container"].shutdown.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_fails_when_prometheus_exporter_unavailable_and_shuts_down(
    main_mocks: dict[str, MagicMock | AsyncMock],
) -> None:
    main_mocks["container"].observe.collector.serve.side_effect = PrometheusHttpExporterError("down")

    with (
        patch("main.Config", return_value=main_mocks["config"]),
        patch("main.Container", return_value=main_mocks["container"]),
        patch("main.Bot", return_value=main_mocks["bot"]),
        patch("main.Dispatcher", return_value=main_mocks["dp"]),
        patch("main.setup_bot"),
        patch("main.setup_dp"),
        pytest.raises(PrometheusHttpExporterError, match="down"),
    ):
        await main()

    main_mocks["dp"].start_polling.assert_not_called()
    main_mocks["bot"].session.close.assert_awaited_once()
    main_mocks["container"].shutdown.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_reraises_polling_error_and_still_shuts_down(
    main_mocks: dict[str, MagicMock | AsyncMock],
) -> None:
    main_mocks["dp"].start_polling.side_effect = RuntimeError("polling failed")

    with (
        patch("main.Config", return_value=main_mocks["config"]),
        patch("main.Container", return_value=main_mocks["container"]),
        patch("main.Bot", return_value=main_mocks["bot"]),
        patch("main.Dispatcher", return_value=main_mocks["dp"]),
        patch("main.setup_bot"),
        patch("main.setup_dp"),
        pytest.raises(RuntimeError, match="polling failed"),
    ):
        await main()

    main_mocks["bot"].session.close.assert_awaited_once()
    main_mocks["container"].shutdown.assert_awaited_once()
