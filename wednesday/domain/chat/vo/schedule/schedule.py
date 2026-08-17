from dataclasses import dataclass
from typing import ClassVar, Self

from ...exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ChatSchedule:
    """Value Object: message delivery schedule for a chat."""

    _MAX_HOUR: ClassVar[int] = 23
    _MAX_MINUTE: ClassVar[int] = 59

    hour: int
    minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= self._MAX_HOUR:
            raise ValidationError(f"Hour must be 0-23, got {self.hour}")
        if not 0 <= self.minute <= self._MAX_MINUTE:
            raise ValidationError(f"Minute must be 0-59, got {self.minute}")

    @classmethod
    def ensure(cls, schedule: Self) -> Self:
        if not isinstance(schedule, cls):
            raise ValidationError("schedule must be a ChatSchedule")
        return schedule
