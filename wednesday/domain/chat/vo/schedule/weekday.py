from enum import IntEnum
from typing import Self

from ...exceptions import ValidationError


class Weekday(IntEnum):
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7

    @classmethod
    def ensure(cls, weekday: Self) -> Self:
        if not isinstance(weekday, cls):
            raise ValidationError("weekday must be a Weekday")
        return weekday
