from enum import Enum

from asyncbreaker.state import CircuitBreakerBaseState


class CircuitState(float, Enum):
    CLOSED = 0.0
    HALF_OPEN = 0.5
    OPEN = 1.0
    UNKNOWN = -1.0

    def __str__(self) -> str:
        return self.name.lower()

    @classmethod
    def from_external(cls, external_state: CircuitBreakerBaseState) -> "CircuitState":
        try:
            return cls[external_state.state.name]
        except (KeyError, AttributeError):
            return cls.UNKNOWN
