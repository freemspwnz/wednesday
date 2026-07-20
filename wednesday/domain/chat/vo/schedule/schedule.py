from dataclasses import dataclass
from typing import Self

from ...exceptions import ValidationError

MAX_HOUR = 23
MAX_MINUTE = 59


@dataclass(frozen=True, slots=True)
class ChatSchedule:
    """Value Object: message delivery schedule for a chat."""

    hour: int
    minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= MAX_HOUR:
            raise ValidationError(f"Hour must be 0-23, got {self.hour}")
        if not 0 <= self.minute <= MAX_MINUTE:
            raise ValidationError(f"Minute must be 0-59, got {self.minute}")

    @classmethod
    def ensure(cls, schedule: Self) -> Self:
        if not isinstance(schedule, cls):
            raise ValidationError("schedule must be a ChatSchedule")
        return schedule
