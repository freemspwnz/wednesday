"""Shared fixtures for the ``tests/infra/`` tree."""

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def isolate_loguru() -> Iterator[None]:
    """Reset loguru handlers between tests (observe, di, etc.)."""
    logger.remove()
    yield
    logger.remove()


@pytest.fixture
def mock_logger() -> MagicMock:
    log = MagicMock()
    log.bind.return_value = log
    return log
