from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from ...exceptions import ScheduleLimitExceededError, ValidationError
from .schedule import ChatSchedule
from .weekday import Weekday

MAX_SCHEDULES = 3


@dataclass(frozen=True, slots=True)
class ChatScheduleSet:
    """Value Object: chat schedule settings."""

    timezone: ZoneInfo
    weekday: Weekday = Weekday.WEDNESDAY
    schedules: tuple[ChatSchedule, ...] = ()

    def __post_init__(self) -> None:
        Weekday.ensure(self.weekday)
        for schedule in self.schedules:
            ChatSchedule.ensure(schedule)
        if not isinstance(self.timezone, ZoneInfo):
            raise ValidationError("timezone must be a ZoneInfo")
        if len(self.schedules) > MAX_SCHEDULES:
            raise ScheduleLimitExceededError(MAX_SCHEDULES)

    def change_timezone(self, timezone: ZoneInfo) -> ChatScheduleSet:
        if timezone == self.timezone:
            return self
        return ChatScheduleSet(timezone=timezone, weekday=self.weekday, schedules=self.schedules)

    def change_day(self, weekday: Weekday) -> ChatScheduleSet:
        if weekday == self.weekday:
            return self
        return ChatScheduleSet(timezone=self.timezone, weekday=weekday, schedules=self.schedules)

    def add(self, schedule: ChatSchedule) -> ChatScheduleSet:
        if len(self.schedules) >= MAX_SCHEDULES:
            raise ScheduleLimitExceededError(MAX_SCHEDULES)
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
    def ensure(cls, schedule_set: ChatScheduleSet) -> ChatScheduleSet:
        if not isinstance(schedule_set, cls):
            raise ValidationError("schedule_set must be a ChatScheduleSet")
        return schedule_set
