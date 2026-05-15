"""Тесты утилит Redis-репозиториев."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from infra.persistence.redis.repos.utils import (
    log_warning_and_invalidate_cache_key,
    raw_to_text,
    ttl_to_seconds,
)


@pytest.mark.unit
class TestRawToText:
    def test_none(self) -> None:
        assert raw_to_text(None) is None

    def test_str(self) -> None:
        assert raw_to_text("x") == "x"

    def test_bytes_utf8(self) -> None:
        assert raw_to_text(b"ab") == "ab"

    def test_other_coerced_to_str(self) -> None:
        assert raw_to_text(123) == "123"


@pytest.mark.unit
class TestTtlToSeconds:
    def test_none(self) -> None:
        assert ttl_to_seconds(None) is None

    def test_int(self) -> None:
        assert ttl_to_seconds(60) == 60

    def test_timedelta(self) -> None:
        assert ttl_to_seconds(timedelta(minutes=5)) == 300


@pytest.mark.unit
class TestLogWarningAndInvalidate:
    @pytest.mark.asyncio
    async def test_logs_and_deletes_key(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.delete = AsyncMock()

        await log_warning_and_invalidate_cache_key(
            client=client,
            logger=mock_logger,
            key="ctx:user:1",
            message="bad cache",
        )

        mock_logger.warning.assert_called_once_with("bad cache", key="ctx:user:1", exc_info=False)
        client.delete.assert_awaited_once_with("ctx:user:1")

    @pytest.mark.asyncio
    async def test_passes_exc_info(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.delete = AsyncMock()

        await log_warning_and_invalidate_cache_key(
            client=client,
            logger=mock_logger,
            key="k",
            message="m",
            exc_info=True,
        )

        mock_logger.warning.assert_called_once_with("m", key="k", exc_info=True)
