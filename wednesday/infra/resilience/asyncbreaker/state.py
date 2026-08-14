from enum import Enum
from typing import Self

from asyncbreaker import CircuitState as LibState


class CircuitState(float, Enum):
    CLOSED = 0.0
    HALF_OPEN = 0.5
    OPEN = 1.0
    UNKNOWN = -1.0

    def __str__(self) -> str:
        return self.name.lower()

    @classmethod
    def from_library(cls, state: LibState) -> Self:
        try:
            return cls[state.name]
        except KeyError:
            return cls.UNKNOWN
