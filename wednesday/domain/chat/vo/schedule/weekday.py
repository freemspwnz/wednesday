from __future__ import annotations

from enum import IntEnum

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
    def ensure(cls, weekday: Weekday) -> Weekday:
        if not isinstance(weekday, cls):
            raise ValidationError("weekday must be a Weekday")
        return weekday
