from __future__ import annotations

from dataclasses import dataclass
from typing import Final
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

    def change_timezone(self, timezone: ZoneInfo) -> ChatScheduleSet:
        if timezone == self.timezone:
            return self
        return ChatScheduleSet(timezone=timezone, weekday=self.weekday, schedules=self.schedules)

    def change_day(self, weekday: Weekday) -> ChatScheduleSet:
        if weekday == self.weekday:
            return self
        return ChatScheduleSet(timezone=self.timezone, weekday=weekday, schedules=self.schedules)

    def add(self, schedule: ChatSchedule) -> ChatScheduleSet:
        if len(self.schedules) >= self.MAX_SCHEDULES:
            raise ScheduleLimitExceededError(self.MAX_SCHEDULES)
        if schedule in self.schedules:
            return self
        return ChatScheduleSet(timezone=self.timezone, weekday=self.weekday, schedules=(*self.schedules, schedule))

    def remove(self, schedule: ChatSchedule) -> ChatScheduleSet:
        if schedule not in self.schedules:
            return self
        new = tuple(s for s in self.schedules if s != schedule)
        return ChatScheduleSet(
            timezone=self.timezone,
            weekday=self.weekday,
            schedules=new,
        )

    def clear(self) -> ChatScheduleSet:
        if self.schedules != ():
            return ChatScheduleSet(timezone=self.timezone, weekday=self.weekday, schedules=())
        return self

    @classmethod
    def ensure(cls, set: ChatScheduleSet) -> ChatScheduleSet:
        if not isinstance(set, cls):
            raise ValidationError("set must be a ChatScheduleSet")
        return set
