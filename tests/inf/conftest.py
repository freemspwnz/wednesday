"""Общие фикстуры для всего дерева ``tests/infra/``."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def isolate_loguru() -> Iterator[None]:
    """Сбрасывает handlers loguru между тестами (observe, di и др.)."""
    logger.remove()
    yield
    logger.remove()


@pytest.fixture
def mock_logger() -> MagicMock:
    log = MagicMock()
    log.bind.return_value = log
    return log
