from collections.abc import Callable

from asyncbreaker import CircuitBreaker, CircuitBreakerListener
from asyncbreaker.state import CircuitBreakerBaseState

from app.protocols import CBMetrics

from ..state import CircuitState


class MetricsListener(CircuitBreakerListener):
    """
    Circuit breaker state listener.
    """

    def __init__(self, metrics: CBMetrics) -> None:
        self._metrics = metrics

    async def before_call(
        self,
        cb: CircuitBreaker,
        func: Callable,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._metrics.before_call()

    async def failure(self, cb: CircuitBreaker, exc: Exception) -> None:
        self._metrics.after_call(name=cb.name, result="failure")

    async def success(self, cb: CircuitBreaker) -> None:
        self._metrics.after_call(name=cb.name, result="success")

    async def state_change(
        self,
        cb: CircuitBreaker,
        old: CircuitBreakerBaseState,
        new: CircuitBreakerBaseState,
    ) -> None:
        mapped_new = CircuitState.from_external(new)
        mapped_old = CircuitState.from_external(old)

        self._metrics.on_state_change(
            name=cb.name,
            old_state=str(mapped_old),
            new_state=str(mapped_new),
        )
