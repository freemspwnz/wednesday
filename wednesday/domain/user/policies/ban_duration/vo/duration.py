from dataclasses import dataclass
from datetime import timedelta
from typing import Self

from ....exceptions import ValidationError
from ....vo import AwareDatetime


@dataclass(frozen=True, order=True)
class BanDuration:
    """Value Object: ban duration."""

    value: timedelta

    def __add__(self, other: object) -> AwareDatetime | Self:
        if isinstance(other, AwareDatetime):
            return AwareDatetime(other.value + self.value)

        if isinstance(other, BanDuration):
            return self.__class__(other.value + self.value)

        return NotImplemented

    def __radd__(self, other: AwareDatetime) -> AwareDatetime:
        if isinstance(other, AwareDatetime):
            return AwareDatetime(other.value + self.value)

        return NotImplemented

    def __post_init__(self) -> None:
        if not isinstance(self.value, timedelta):
            raise ValidationError("value must be a timedelta")

        if self.value.total_seconds() < 0:
            raise ValidationError("value must be >= 0")

    @classmethod
    def null(cls) -> Self:
        return cls(value=timedelta(0))

    @classmethod
    def hour(cls) -> Self:
        return cls(value=timedelta(hours=1))

    @classmethod
    def day(cls) -> Self:
        return cls(value=timedelta(days=1))

    @classmethod
    def week(cls) -> Self:
        return cls(value=timedelta(weeks=1))

    @classmethod
    def month(cls) -> Self:
        return cls(value=timedelta(days=30))

    @classmethod
    def year(cls) -> Self:
        return cls(value=timedelta(days=365))
