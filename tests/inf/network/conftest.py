"""Shared fixtures for infra.network httpx2 tests."""

from collections.abc import Awaitable, Callable
from typing import TypeVar
from unittest.mock import MagicMock

import pytest

from infra.config import HttpConfig, HttpTimeoutConfig

T = TypeVar("T")


@pytest.fixture
def mock_http_metrics() -> MagicMock:
    metrics = MagicMock()
    metrics.on_request = MagicMock()
    metrics.on_response = MagicMock()
    metrics.on_error = MagicMock()
    return metrics


@pytest.fixture
def http_config() -> HttpConfig:
    return HttpConfig(
        name="unit",
        base_url="https://api.example.com/v1/",
        verify=False,
        http2=False,
        timeouts={"base": HttpTimeoutConfig(timeout=5, connect=2, read=5, write=2, pool=2)},
    )


class PassThroughRetrier:
    def __call__(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        return func

    async def execute(self, func: Callable[..., Awaitable[T]], *args: object, **kwargs: object) -> T:
        return await func(*args, **kwargs)


class PassThroughBreaker:
    def __call__(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        return func

    async def call(self, func: Callable[..., Awaitable[T]], *args: object, **kwargs: object) -> T:
        return await func(*args, **kwargs)

    async def open(self) -> None:
        return None

    async def half_open(self) -> None:
        return None

    async def close(self) -> None:
        return None


class PassThroughLimiter:
    def __init__(self) -> None:
        self.limits = {"base": "base"}

    def __call__(
        self,
        limit: object,
        *args: str,
        cost: int = 1,
    ) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
        _ = limit, args, cost

        def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
            return func

        return decorator

    async def call(self, limit: object, *args: str, cost: int = 1) -> None:
        _ = limit, args, cost

    async def test(self, limit: object, *args: str, cost: int = 1) -> None:
        _ = limit, args, cost

    async def reset(self, limit: object, *args: str) -> None:
        _ = limit, args

    async def get_window_stats(self, limit: object, *args: str) -> object:
        _ = limit, args
        return object()
