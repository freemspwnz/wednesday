from dataclasses import dataclass
from zoneinfo import ZoneInfo

from ..exceptions import ValidationError
from ..vo import (
    ChatSchedule,
    ManagementActor,
    Weekday,
)
from .base import ChatEvent


@dataclass(frozen=True)
class ChatScheduleTimezoneChanged(ChatEvent):
    old_timezone: ZoneInfo
    new_timezone: ZoneInfo
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.old_timezone, ZoneInfo):
            raise ValidationError("old_timezone must be a ZoneInfo")
        if not isinstance(self.new_timezone, ZoneInfo):
            raise ValidationError("new_timezone must be a ZoneInfo")
        ManagementActor.ensure(self.actor)


@dataclass(frozen=True)
class ChatScheduleDayChanged(ChatEvent):
    old_weekday: Weekday
    new_weekday: Weekday
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        Weekday.ensure(self.old_weekday)
        Weekday.ensure(self.new_weekday)
        ManagementActor.ensure(self.actor)


@dataclass(frozen=True)
class ChatScheduleAdded(ChatEvent):
    schedule: ChatSchedule
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        ChatSchedule.ensure(self.schedule)
        ManagementActor.ensure(self.actor)


@dataclass(frozen=True)
class ChatScheduleRemoved(ChatEvent):
    schedule: ChatSchedule
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        ChatSchedule.ensure(self.schedule)
        ManagementActor.ensure(self.actor)


@dataclass(frozen=True)
class ChatScheduleCleared(ChatEvent):
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        ManagementActor.ensure(self.actor)
