"""Tests for DIMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from presentation.aiogram.middlewares.update.di import DIMiddleware

from ..factories import ScopeCM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_injects_scope_and_logger(mock_logger: MagicMock) -> None:
    container = MagicMock()
    container.logger = mock_logger
    scope = MagicMock(return_value=ScopeCM(container))

    middleware = DIMiddleware(scope=scope, logger=mock_logger)
    handler = AsyncMock(return_value="done")
    data: dict[str, object] = {}

    result = await middleware(handler, MagicMock(), data)

    assert result == "done"
    assert data["scope"] is container
    assert data["logger"] is mock_logger
    handler.assert_awaited_once()
