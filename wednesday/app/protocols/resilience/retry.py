from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

T = TypeVar("T")


class Retrier(Protocol):
    def __call__(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]: ...

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T: ...
