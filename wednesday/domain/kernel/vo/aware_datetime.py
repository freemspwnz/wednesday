from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Self, overload

from ..exceptions import ValidationError


@dataclass(frozen=True, order=True)
class AwareDatetime:
    """Time with timezone."""

    value: datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            raise ValidationError("datetime must be timezone-aware")

    def __str__(self) -> str:
        return self.value.isoformat()

    def __add__(self, other: timedelta) -> Self:
        if not isinstance(other, timedelta):
            return NotImplemented
        return self.__class__(self.value + other)

    @overload
    def __sub__(self, other: timedelta) -> Self: ...

    @overload
    def __sub__(self, other: Self) -> timedelta: ...

    def __sub__(self, other: object) -> Self | timedelta:
        if isinstance(other, timedelta):
            return self.__class__(self.value - other)
        if isinstance(other, AwareDatetime):
            return self.value - other.value  # returns timedelta
        return NotImplemented

    def __repr__(self) -> str:
        return f"AwareDatetime({self.value!r})"

    @classmethod
    def now_utc(cls) -> Self:
        return cls(value=datetime.now(UTC))

    @classmethod
    def from_datetime(cls, dt: datetime) -> Self:
        return cls(value=dt)

    @classmethod
    def ensure(cls, dt: object) -> Self:
        if not isinstance(dt, cls):
            raise ValidationError(f"dt must be a {cls.__name__}")
        return dt
