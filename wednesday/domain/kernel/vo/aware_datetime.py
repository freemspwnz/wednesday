from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import overload

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

    def __add__(self, other: timedelta) -> AwareDatetime:
        if not isinstance(other, timedelta):
            return NotImplemented
        return AwareDatetime(self.value + other)

    @overload
    def __sub__(self, other: timedelta) -> AwareDatetime: ...

    @overload
    def __sub__(self, other: AwareDatetime) -> timedelta: ...

    def __sub__(self, other: object) -> AwareDatetime | timedelta:
        if isinstance(other, timedelta):
            return AwareDatetime(self.value - other)
        if isinstance(other, AwareDatetime):
            return self.value - other.value  # returns timedelta
        return NotImplemented

    def __repr__(self) -> str:
        return f"AwareDatetime({self.value!r})"

    @classmethod
    def now_utc(cls) -> AwareDatetime:
        return cls(value=datetime.now(UTC))

    @classmethod
    def from_datetime(cls, dt: datetime) -> AwareDatetime:
        return cls(value=dt)
