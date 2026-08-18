"""Main entry point tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from main import main

from app.exceptions import CacheUnavailableError, DBUnavailableError, MetricsHttpExporterError


@pytest.fixture
def main_mocks() -> dict[str, MagicMock | AsyncMock]:
    config = MagicMock()
    config.telegram.token.get_secret_value.return_value = "test-token"
    config.telegram.admin_id = 1
    config.telegram.limiter = MagicMock()
    config.telegram.retrier = MagicMock()

    container = MagicMock()
    container.observe.logger.bind.return_value = MagicMock()
    container.observe.metrics = MagicMock()
    container.observe.metrics.serve = MagicMock()
    container.shutdown = AsyncMock()
    container.get_scope = MagicMock()
    container.resilience.limiter.return_value = MagicMock()
    container.resilience.retrier.return_value = MagicMock()
    container.persistence.warmup = AsyncMock()

    bot = MagicMock()
    bot.session.close = AsyncMock()

    dp = MagicMock()
    dp.start_polling = AsyncMock()

    runner = MagicMock()
    runner.run = AsyncMock()

    return {
        "config": config,
        "container": container,
        "bot": bot,
        "dp": dp,
        "runner": runner,
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
        patch("main.CatalogScheduleRunner", return_value=main_mocks["runner"]),
    ):
        await main()

    main_mocks["bot"].session.close.assert_awaited_once()
    main_mocks["container"].shutdown.assert_awaited_once()
    main_mocks["container"].persistence.warmup.assert_awaited_once()
    main_mocks["dp"].start_polling.assert_awaited_once()
    main_mocks["runner"].run.assert_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_fails_when_postgres_unreachable_and_shuts_down(
    main_mocks: dict[str, MagicMock | AsyncMock],
) -> None:
    main_mocks["container"].persistence.warmup.side_effect = DBUnavailableError("down")

    with (
        patch("main.Config", return_value=main_mocks["config"]),
        patch("main.Container", return_value=main_mocks["container"]),
        patch("main.Bot", return_value=main_mocks["bot"]),
        patch("main.Dispatcher", return_value=main_mocks["dp"]),
        patch("main.setup_bot"),
        patch("main.setup_dp"),
        pytest.raises(DBUnavailableError, match="down"),
    ):
        await main()

    main_mocks["container"].observe.metrics.serve.assert_not_called()
    main_mocks["dp"].start_polling.assert_not_called()
    main_mocks["bot"].session.close.assert_awaited_once()
    main_mocks["container"].shutdown.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_fails_when_redis_unreachable_and_shuts_down(
    main_mocks: dict[str, MagicMock | AsyncMock],
) -> None:
    main_mocks["container"].persistence.warmup.side_effect = CacheUnavailableError(
        "down",
        operation="ping",
    )

    with (
        patch("main.Config", return_value=main_mocks["config"]),
        patch("main.Container", return_value=main_mocks["container"]),
        patch("main.Bot", return_value=main_mocks["bot"]),
        patch("main.Dispatcher", return_value=main_mocks["dp"]),
        patch("main.setup_bot"),
        patch("main.setup_dp"),
        pytest.raises(CacheUnavailableError, match="down"),
    ):
        await main()

    main_mocks["container"].observe.metrics.serve.assert_not_called()
    main_mocks["dp"].start_polling.assert_not_called()
    main_mocks["bot"].session.close.assert_awaited_once()
    main_mocks["container"].shutdown.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_fails_when_prometheus_exporter_unavailable_and_shuts_down(
    main_mocks: dict[str, MagicMock | AsyncMock],
) -> None:
    main_mocks["container"].observe.metrics.serve.side_effect = MetricsHttpExporterError("down")

    with (
        patch("main.Config", return_value=main_mocks["config"]),
        patch("main.Container", return_value=main_mocks["container"]),
        patch("main.Bot", return_value=main_mocks["bot"]),
        patch("main.Dispatcher", return_value=main_mocks["dp"]),
        patch("main.setup_bot"),
        patch("main.setup_dp"),
        pytest.raises(MetricsHttpExporterError, match="down"),
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
        patch("main.CatalogScheduleRunner", return_value=main_mocks["runner"]),
        pytest.raises(RuntimeError, match="polling failed"),
    ):
        await main()

    main_mocks["bot"].session.close.assert_awaited_once()
    main_mocks["container"].shutdown.assert_awaited_once()
