from collections.abc import Awaitable, Callable

from asyncbreaker import CircuitBreaker, CircuitState as LibState, Listener

from app.protocols import Logger

from ..state import CircuitState


class LoggingListener(Listener):
    """
    Circuit breaker state listener.
    """

    def __init__(self, logger: Logger) -> None:
        self._logger = logger.bind(module="Asyncbreaker")

    async def before_call(
        self,
        breaker: CircuitBreaker,
        func: Callable[..., Awaitable[object]],
        *args: object,
        **kwargs: object,
    ) -> None:
        self._logger.debug(
            "Asyncbreaker call request",
            name=breaker.name,
            method=func.__name__,
        )

    async def failure(self, breaker: CircuitBreaker, exception: Exception) -> None:
        self._logger.warning(
            "Asyncbreaker call failed",
            name=breaker.name,
            exception=f"{exception!r}",
        )

    async def success(self, breaker: CircuitBreaker) -> None:
        self._logger.debug(
            "Asyncbreaker call succeeded",
            name=breaker.name,
        )

    async def state_change(
        self,
        breaker: CircuitBreaker,
        old: LibState,
        new: LibState,
    ) -> None:
        mapped_old = CircuitState.from_library(old)
        mapped_new = CircuitState.from_library(new)
        self._logger.info(
            "Asyncbreaker state changed",
            name=breaker.name,
            old_state=str(mapped_old),
            new_state=str(mapped_new),
        )
