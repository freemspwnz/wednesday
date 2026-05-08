from __future__ import annotations

from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .events import (
    ChatActivated,
    ChatDeactivated,
    ChatEvent,
    ChatProfileChanged,
    ChatScheduleAdded,
    ChatScheduleCleared,
    ChatScheduleDayChanged,
    ChatScheduleRemoved,
    ChatScheduleTimezoneChanged,
)
from .exceptions import ManagementAccessDeniedError, StaleWriteError, ValidationError
from .policies import (
    ManagementAccessPolicy,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
)
from .vo import (
    ActiveState,
    AwareDatetime,
    ChatId,
    ChatProfile,
    ChatSchedule,
    ChatScheduleSet,
    ChatState,
    ManagementActor,
    Weekday,
)


@dataclass(slots=True, eq=False)
class Chat:
    """Aggregate Root: Telegram chat (private, group, channel).

    Manages chat settings (schedule) and its lifecycle.
    """

    _id: ChatId
    _profile: ChatProfile
    _state: ChatState
    _schedules: ChatScheduleSet
    _events: list[ChatEvent]

    _created_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)
    _updated_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)

    def __post_init__(self) -> None:
        self._validate()

    @classmethod
    def register(
        cls,
        id: ChatId,
        profile: ChatProfile,
        schedules: ChatScheduleSet,
        at: AwareDatetime,
    ) -> Chat:
        return cls(
            _id=id,
            _profile=profile,
            _state=ActiveState(),
            _schedules=schedules,
            _events=[],
            _created_at=at,
            _updated_at=at,
        )

    @classmethod
    def restore(  # noqa: PLR0917, PLR0913
        cls,
        id: ChatId,
        profile: ChatProfile,
        state: ChatState,
        schedules: ChatScheduleSet,
        created_at: AwareDatetime,
        updated_at: AwareDatetime,
    ) -> Chat:
        return cls(
            _id=id,
            _profile=profile,
            _state=state,
            _schedules=schedules,
            _events=[],
            _created_at=created_at,
            _updated_at=updated_at,
        )

    @classmethod
    def ensure(cls, chat: Chat) -> Chat:
        if not isinstance(chat, Chat):
            raise ValidationError("chat must be a Chat")
        return chat

    @property
    def id(self) -> ChatId:
        return self._id

    @property
    def profile(self) -> ChatProfile:
        return self._profile

    @property
    def state(self) -> ChatState:
        return self._state

    @property
    def schedules(self) -> ChatScheduleSet:
        return self._schedules

    @property
    def created_at(self) -> AwareDatetime:
        return self._created_at

    @property
    def updated_at(self) -> AwareDatetime:
        return self._updated_at

    def pull_events(self) -> list[ChatEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def change_profile(self, *, actor: ManagementActor, new_profile: ChatProfile, at: AwareDatetime) -> None:
        actor = ManagementActor.ensure(actor)
        new_profile = ChatProfile.ensure(new_profile)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor)

        if new_profile != self._profile:
            self._update_at(at)
            old = self._profile
            self._profile = new_profile
            self._record_event(
                ChatProfileChanged(
                    chat_id=self._id,
                    occurred_at=at,
                    actor=actor,
                    old_profile=old,
                    new_profile=self._profile,
                )
            )

    def change_schedule_day(
        self,
        *,
        actor: ManagementActor,
        new_weekday: Weekday,
        at: AwareDatetime,
    ) -> None:
        actor = ManagementActor.ensure(actor)
        new_weekday = Weekday.ensure(new_weekday)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor)

        new = self._schedules.change_day(new_weekday)
        if new != self._schedules:
            self._update_at(at)
            old = self._schedules.weekday
            self._schedules = new
            self._record_event(
                ChatScheduleDayChanged(
                    chat_id=self._id,
                    occurred_at=at,
                    actor=actor,
                    old_weekday=old,
                    new_weekday=self._schedules.weekday,
                )
            )

    def change_schedule_timezone(
        self,
        *,
        actor: ManagementActor,
        timezone: ZoneInfo,
        at: AwareDatetime,
    ) -> None:
        actor = ManagementActor.ensure(actor)
        at = AwareDatetime.ensure(at)
        if not isinstance(timezone, ZoneInfo):
            raise ValidationError("timezone must be a ZoneInfo")
        self._ensure_management_allowed(actor)

        new = self._schedules.change_timezone(timezone)
        if new != self._schedules:
            self._update_at(at)
            old = self._schedules.timezone
            self._schedules = new
            self._record_event(
                ChatScheduleTimezoneChanged(
                    chat_id=self._id,
                    occurred_at=at,
                    actor=actor,
                    old_timezone=old,
                    new_timezone=self._schedules.timezone,
                )
            )

    def add_schedule(
        self,
        *,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> None:
        actor = ManagementActor.ensure(actor)
        schedule = ChatSchedule.ensure(schedule)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor)

        new = self._schedules.add(schedule)
        if new != self._schedules:
            self._update_at(at)
            self._schedules = new
            self._record_event(
                ChatScheduleAdded(
                    chat_id=self._id,
                    occurred_at=at,
                    actor=actor,
                    schedule=schedule,
                )
            )

    def remove_schedule(
        self,
        *,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> None:
        actor = ManagementActor.ensure(actor)
        schedule = ChatSchedule.ensure(schedule)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor)

        new = self._schedules.remove(schedule)
        if new != self._schedules:
            self._update_at(at)
            self._schedules = new
            self._record_event(
                ChatScheduleRemoved(
                    chat_id=self._id,
                    occurred_at=at,
                    actor=actor,
                    schedule=schedule,
                )
            )

    def clear_schedules(self, *, actor: ManagementActor, at: AwareDatetime) -> None:
        actor = ManagementActor.ensure(actor)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor)

        new = self._schedules.clear()
        if new != self._schedules:
            self._update_at(at)
            self._schedules = new
            self._record_event(
                ChatScheduleCleared(
                    chat_id=self._id,
                    occurred_at=at,
                    actor=actor,
                )
            )

    def activate(self, *, actor: ManagementActor, at: AwareDatetime) -> None:
        actor = ManagementActor.ensure(actor)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor)

        new = self._state.activate()
        self._update_at(at)
        self._state = new
        self._record_event(
            ChatActivated(
                chat_id=self._id,
                occurred_at=at,
                actor=actor,
            )
        )

    def deactivate(self, *, actor: ManagementActor, at: AwareDatetime) -> None:
        actor = ManagementActor.ensure(actor)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor)

        new = self._state.deactivate()
        self._update_at(at)
        self._state = new
        self._record_event(
            ChatDeactivated(
                chat_id=self._id,
                occurred_at=at,
                actor=actor,
            )
        )

    def _record_event(self, event: ChatEvent) -> None:
        self._events.append(event)

    def _ensure_management_allowed(
        self,
        actor: ManagementActor,
    ) -> None:
        ManagementActor.ensure(actor)

        ctx = ManagementContext(actor=actor, chat_id=self._id)
        decision = ManagementAccessPolicy.evaluate(ctx)
        match decision:
            case ManagementAllowed():
                return
            case ManagementDenied():
                raise ManagementAccessDeniedError(decision.code)
            case _:
                raise ValidationError("unknown management decision")

    def _update_at(self, at: AwareDatetime) -> None:
        if at < self._updated_at:
            raise StaleWriteError("at must be >= updated_at")

        self._updated_at = at

    def _validate(self) -> None:
        ChatId.ensure(self._id)
        ChatProfile.ensure(self._profile)
        ChatState.ensure(self._state)
        ChatScheduleSet.ensure(self._schedules)
        if not isinstance(self._events, list):
            raise ValidationError("events must be a list[ChatEvent]")
        for event in self._events:
            ChatEvent.ensure(event)
        AwareDatetime.ensure(self._created_at)
        AwareDatetime.ensure(self._updated_at)
        if self._created_at > self._updated_at:
            raise ValidationError("created_at must be <= updated_at")
