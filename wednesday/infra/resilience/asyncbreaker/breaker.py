from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

from asyncbreaker import CircuitBreaker as Breaker, CircuitBreakerError, StorageError

from app.exceptions import AppError, CircuitOpenError, CircuitStorageError, UnexpectedCircuitError
from app.protocols import CircuitBreaker, Logger

T = TypeVar("T")


class Asyncbreaker(CircuitBreaker):
    def __init__(
        self,
        *,
        breaker: Breaker,
        logger: Logger,
    ) -> None:
        self._breaker = breaker
        self._logger = logger.bind(module=self.__class__.__name__, service=breaker.name)

    def __call__(
        self,
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            return await self.call(func, *args, **kwargs)

        return wrapper

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        try:
            return await self._breaker.call(func, *args, **kwargs)  # type: ignore[no-any-return]

        except CircuitBreakerError as e:
            retry_after = max(0.0, e.time_remaining.total_seconds())
            raise CircuitOpenError(
                message=f"Circuit {self._breaker.name} is open.",
                retry_after=retry_after,
            ) from e

        except StorageError as e:
            self._logger.error(
                "Circuit breaker storage unavailable",
                name=self._breaker.name,
                exc_info=True,
            )
            raise CircuitStorageError(
                "Circuit breaker storage is unavailable; request rejected.",
            ) from e

        except AppError:
            raise

        except Exception as e:
            self._logger.exception(
                "Circuit breaker unexpected error",
                name=self._breaker.name,
                exc_info=True,
            )
            raise UnexpectedCircuitError(
                "Circuit breaker unexpected error; request rejected.",
            ) from e

    async def open(self) -> None:
        try:
            await self._breaker.open()

        except StorageError as e:
            self._logger.error(
                "Circuit breaker storage error",
                name=self._breaker.name,
                exc_info=True,
            )
            raise CircuitStorageError(
                "Circuit breaker storage is unavailable; request rejected.",
            ) from e

    async def half_open(self) -> None:
        try:
            await self._breaker.half_open()

        except StorageError as e:
            self._logger.error(
                "Circuit breaker storage error",
                name=self._breaker.name,
                exc_info=True,
            )
            raise CircuitStorageError(
                "Circuit breaker storage is unavailable; request rejected.",
            ) from e

    async def close(self) -> None:
        try:
            await self._breaker.close()

        except StorageError as e:
            self._logger.error(
                "Circuit breaker storage error",
                name=self._breaker.name,
                exc_info=True,
            )
            raise CircuitStorageError(
                "Circuit breaker storage is unavailable; request rejected.",
            ) from e
