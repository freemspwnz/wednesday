"""Tests for DIMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from presentation.aiogram.middlewares.update.di import DIMiddleware

from ..factories import ScopeCM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_injects_scope_and_logger(mock_logger: MagicMock) -> None:
    scope = MagicMock()
    scope.logger = mock_logger
    factory = MagicMock(return_value=ScopeCM(scope))
    middleware = DIMiddleware(scope_factory=factory, logger=mock_logger)
    handler = AsyncMock(return_value="done")
    data: dict[str, object] = {}

    result = await middleware(handler, MagicMock(), data)

    assert result == "done"
    assert data["scope"] is scope
    assert data["logger"] is mock_logger
    handler.assert_awaited_once()
