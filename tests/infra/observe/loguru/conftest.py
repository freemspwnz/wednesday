"""Изоляция глобального loguru между тестами."""

from collections.abc import Iterator

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def isolate_loguru() -> Iterator[None]:
    logger.remove()
    yield
    logger.remove()
