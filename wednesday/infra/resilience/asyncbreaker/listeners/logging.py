from collections.abc import Callable

from asyncbreaker import CircuitBreaker, CircuitBreakerListener
from asyncbreaker.state import CircuitBreakerBaseState

from app.protocols import Logger

from ..state import CircuitState


class LoggingListener(CircuitBreakerListener):
    """
    Circuit breaker state listener.
    """

    def __init__(self, logger: Logger) -> None:
        self._logger = logger.bind(module="Asyncbreaker")

    async def before_call(self, cb: CircuitBreaker, func: Callable, *args: object, **kwargs: object) -> None:
        self._logger.debug(
            "Asyncbreaker call request",
            name=cb.name,
            method=func.__name__,
        )

    async def failure(self, cb: CircuitBreaker, exc: Exception) -> None:
        self._logger.warning(
            "Asyncbreaker call failed",
            name=cb.name,
            exception=f"{exc!r}",
        )

    async def success(self, cb: CircuitBreaker) -> None:
        self._logger.debug(
            "Asyncbreaker call succeeded",
            name=cb.name,
        )

    async def state_change(
        self,
        cb: CircuitBreaker,
        old_state: CircuitBreakerBaseState,
        new_state: CircuitBreakerBaseState,
    ) -> None:
        mapped_old = CircuitState.from_external(old_state)
        mapped_new = CircuitState.from_external(new_state)
        self._logger.info(
            "Asyncbreaker state changed",
            name=cb.name,
            old_state=str(mapped_old),
            new_state=str(mapped_new),
        )
