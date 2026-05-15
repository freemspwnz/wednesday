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
        self._logger = logger

    async def before_call(self, cb: CircuitBreaker, func: Callable, *args: object, **kwargs: object) -> None:
        self._logger.debug(f"Asyncbreaker {cb.name} called method {func.__name__}")

    async def failure(self, cb: CircuitBreaker, exc: Exception) -> None:
        self._logger.warning(f"Asyncbreaker {cb.name} call failed with exception: {exc!r}")

    async def success(self, cb: CircuitBreaker) -> None:
        self._logger.debug(f"Asyncbreaker {cb.name} call succeeded")

    async def state_change(
        self,
        cb: CircuitBreaker,
        old_state: CircuitBreakerBaseState,
        new_state: CircuitBreakerBaseState,
    ) -> None:
        mapped_old = CircuitState.from_external(old_state)
        mapped_new = CircuitState.from_external(new_state)
        self._logger.info(f"Asyncbreaker {cb.name} state changed from {mapped_old} to {mapped_new}")
