from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

T = TypeVar("T")


class IRetryPolicy(Protocol):
    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T: ...
