from dataclasses import dataclass, replace
from typing import Final, Self
from zoneinfo import ZoneInfo

from ...exceptions import ScheduleLimitExceededError, ValidationError
from .schedule import ChatSchedule
from .weekday import Weekday


@dataclass(frozen=True, slots=True)
class ChatScheduleSet:
    """Value Object: chat schedule settings."""

    timezone: ZoneInfo
    weekday: Weekday = Weekday.WEDNESDAY
    schedules: tuple[ChatSchedule, ...] = ()
    MAX_SCHEDULES: Final[int] = 3

    def __post_init__(self) -> None:
        Weekday.ensure(self.weekday)
        for schedule in self.schedules:
            ChatSchedule.ensure(schedule)
        if not isinstance(self.timezone, ZoneInfo):
            raise ValidationError("timezone must be a ZoneInfo")
        if len(self.schedules) > self.MAX_SCHEDULES:
            raise ScheduleLimitExceededError(self.MAX_SCHEDULES)

    def change_timezone(self, timezone: ZoneInfo) -> Self:
        if timezone == self.timezone:
            return self
        return replace(self, timezone=timezone)

    def change_day(self, weekday: Weekday) -> Self:
        if weekday == self.weekday:
            return self
        return replace(self, weekday=weekday)

    def add(self, schedule: ChatSchedule) -> Self:
        if len(self.schedules) >= self.MAX_SCHEDULES:
            raise ScheduleLimitExceededError(self.MAX_SCHEDULES)
        if schedule in self.schedules:
            return self
        return replace(self, schedules=(*self.schedules, schedule))

    def remove(self, schedule: ChatSchedule) -> Self:
        if schedule not in self.schedules:
            return self
        new = tuple(s for s in self.schedules if s != schedule)
        return replace(self, schedules=new)

    def clear(self) -> Self:
        if self.schedules != ():
            return replace(self, schedules=())
        return self

    @classmethod
    def ensure(cls, set: object) -> Self:
        if not isinstance(set, cls):
            raise ValidationError(f"set must be a {cls.__name__}")
        return set
