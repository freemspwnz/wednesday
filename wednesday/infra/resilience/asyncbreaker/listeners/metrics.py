from collections.abc import Awaitable, Callable

from asyncbreaker import CircuitBreaker, CircuitState as LibState, Listener

from app.protocols import CBMetrics

from ..state import CircuitState


class MetricsListener(Listener):
    """
    Circuit breaker state listener.
    """

    def __init__(self, metrics: CBMetrics) -> None:
        self._metrics = metrics

    async def before_call(
        self,
        breaker: CircuitBreaker,
        func: Callable[..., Awaitable[object]],
        *args: object,
        **kwargs: object,
    ) -> None:
        self._metrics.before_call()

    async def failure(self, breaker: CircuitBreaker, exception: Exception) -> None:
        name = breaker.name or "unknown"
        self._metrics.after_call(name=name, result="failure")

    async def success(self, breaker: CircuitBreaker) -> None:
        name = breaker.name or "unknown"
        self._metrics.after_call(name=name, result="success")

    async def state_change(
        self,
        breaker: CircuitBreaker,
        old: LibState,
        new: LibState,
    ) -> None:
        name = breaker.name or "unknown"
        mapped_new = CircuitState.from_library(new)
        mapped_old = CircuitState.from_library(old)

        self._metrics.on_state_change(
            name=name,
            old_state=str(mapped_old),
            new_state=str(mapped_new),
        )
