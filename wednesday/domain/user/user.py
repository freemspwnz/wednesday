from __future__ import annotations

from dataclasses import dataclass, field

from .events import (
    UserBanExpired,
    UserBanned,
    UserEvent,
    UserProfileChanged,
    UserRoleChanged,
    UserSubscriptionChanged,
    UserSubscriptionExpired,
    UserUnbanned,
)
from .exceptions import AccessDeniedError, InvalidStateTransitionError, ValidationError
from .policies import (
    ChangeProfile,
    ChangeRole,
    ChangeState,
    ChangeSubscription,
    ManagementAccessPolicy,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
)
from .vo import (
    ActiveState,
    AwareDatetime,
    UserProfile,
    UserRole,
    UserState,
    UserSubscription,
    UserTelegramId,
)


@dataclass(slots=True, eq=False)
class User:
    _id: UserTelegramId
    _profile: UserProfile
    _role: UserRole
    _state: UserState
    _subscription: UserSubscription
    _events: list[UserEvent]

    _last_seen_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)
    _updated_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)
    _created_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)

    def __post_init__(self) -> None:
        if not isinstance(self._id, UserTelegramId):
            raise ValidationError("id must be a UserTelegramId")
        if not isinstance(self._profile, UserProfile):
            raise ValidationError("profile must be a UserProfile")
        if not isinstance(self._role, UserRole):
            raise ValidationError("role must be a UserRole")
        if not isinstance(self._state, UserState):
            raise ValidationError("state must be a UserState")
        if not isinstance(self._subscription, UserSubscription):
            raise ValidationError("subscription must be a UserSubscription")
        if not isinstance(self._events, list):
            raise ValidationError("events must be a list[UserEvent]")
        if any(not isinstance(e, UserEvent) for e in self._events):
            raise ValidationError("all events items must be UserEvent")
        if self._created_at > self._updated_at:
            raise ValidationError("created_at must be <= updated_at")
        if self._created_at > self._last_seen_at:
            raise ValidationError("created_at must be <= last_seen_at")

    @classmethod
    def create(
        cls,
        *,
        id: UserTelegramId,
        profile: UserProfile,
        role: UserRole,
        subscription: UserSubscription,
        now: AwareDatetime,
    ) -> User:
        now = AwareDatetime.ensure(now)
        return cls(
            _id=id,
            _profile=profile,
            _role=role,
            _state=ActiveState(),
            _subscription=subscription,
            _events=[],
            _created_at=now,
            _updated_at=now,
            _last_seen_at=now,
        )

    @classmethod
    def rehydrate(  # noqa: PLR0913
        cls,
        *,
        id: UserTelegramId,
        profile: UserProfile,
        role: UserRole,
        state: UserState,
        subscription: UserSubscription,
        created_at: AwareDatetime,
        updated_at: AwareDatetime,
        last_seen_at: AwareDatetime,
    ) -> User:
        return cls(
            _id=id,
            _profile=profile,
            _role=role,
            _state=state,
            _subscription=subscription,
            _events=[],
            _created_at=created_at,
            _updated_at=updated_at,
            _last_seen_at=last_seen_at,
        )

    @property
    def id(self) -> UserTelegramId:
        return self._id

    @property
    def profile(self) -> UserProfile:
        return self._profile

    @property
    def role(self) -> UserRole:
        return self._role

    @property
    def state(self) -> UserState:
        return self._state

    @property
    def subscription(self) -> UserSubscription:
        return self._subscription

    @property
    def created_at(self) -> AwareDatetime:
        return self._created_at

    @property
    def updated_at(self) -> AwareDatetime:
        return self._updated_at

    @property
    def last_seen_at(self) -> AwareDatetime:
        return self._last_seen_at

    def pull_events(self) -> list[UserEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def change_role(
        self,
        *,
        actor: UserRole,
        new_role: UserRole,
        at: AwareDatetime,
    ) -> bool:
        actor = UserRole.ensure(actor)
        new_role = UserRole.ensure(new_role)
        at = AwareDatetime.ensure(at)
        action = ChangeRole(old_role=self._role, new_role=new_role)
        self._assert_management_allowed(actor=actor, action=action)

        if new_role == self._role:
            return False

        self._update_at(at)
        old_role = self._role
        self._role = new_role
        self._record_event(
            UserRoleChanged(
                user_id=self._id,
                occurred_at=at,
                old_role=old_role,
                new_role=new_role,
            )
        )
        return True

    def change_profile(
        self,
        *,
        actor: UserRole,
        new_profile: UserProfile,
        at: AwareDatetime,
    ) -> bool:
        actor = UserRole.ensure(actor)
        if not isinstance(new_profile, UserProfile):
            raise ValidationError("new_profile must be a UserProfile")
        at = AwareDatetime.ensure(at)
        action = ChangeProfile(old_profile=self._profile, new_profile=new_profile)
        self._assert_management_allowed(actor=actor, action=action)

        if new_profile == self._profile:
            return False

        self._update_at(at)
        old_profile = self._profile
        self._profile = new_profile
        self._record_event(
            UserProfileChanged(
                user_id=self._id,
                occurred_at=at,
                old_profile=old_profile,
                new_profile=new_profile,
            )
        )
        return True

    def change_subscription(
        self,
        *,
        actor: UserRole,
        new_subscription: UserSubscription,
        at: AwareDatetime,
    ) -> bool:
        actor = UserRole.ensure(actor)
        if not isinstance(new_subscription, UserSubscription):
            raise ValidationError("new_subscription must be a UserSubscription")
        at = AwareDatetime.ensure(at)
        action = ChangeSubscription(
            old_subscription=self._subscription,
            new_subscription=new_subscription,
        )
        self._assert_management_allowed(actor=actor, action=action)

        if new_subscription == self._subscription:
            return False

        self._update_at(at)
        old_subscription = self._subscription
        self._subscription = new_subscription
        self._record_event(
            UserSubscriptionChanged(
                user_id=self._id,
                occurred_at=at,
                old_subscription=old_subscription,
                new_subscription=new_subscription,
            )
        )
        return True

    def ban(
        self,
        *,
        actor: UserRole,
        until: AwareDatetime,
        at: AwareDatetime,
    ) -> bool:
        actor = UserRole.ensure(actor)
        until = AwareDatetime.ensure(until)
        at = AwareDatetime.ensure(at)
        next_state = self._state.ban_until(until, at)
        action = ChangeState(old_state=self._state, new_state=next_state)
        self._assert_management_allowed(actor=actor, action=action)

        self._update_at(at)
        self._state = next_state
        self._record_event(
            UserBanned(
                user_id=self._id,
                occurred_at=at,
                until=until,
                actor=actor,
            )
        )
        return True

    def unban(
        self,
        *,
        actor: UserRole,
        at: AwareDatetime,
    ) -> bool:
        actor = UserRole.ensure(actor)
        at = AwareDatetime.ensure(at)
        next_state = self._state.unban()
        action = ChangeState(old_state=self._state, new_state=next_state)
        self._assert_management_allowed(actor=actor, action=action)

        self._update_at(at)
        self._state = next_state
        self._record_event(
            UserUnbanned(
                user_id=self._id,
                occurred_at=at,
                actor=actor,
            )
        )
        return True

    def expire_ban_if_due(self, *, at: AwareDatetime) -> bool:
        at = AwareDatetime.ensure(at)
        next_state = self._state.effective_at(at, ActiveState())
        if next_state == self._state:
            return False

        self._update_at(at)
        self._state = next_state
        self._record_event(
            UserBanExpired(
                user_id=self._id,
                occurred_at=at,
            )
        )
        return True

    def expire_subscription_if_due(self, *, at: AwareDatetime) -> bool:
        at = AwareDatetime.ensure(at)
        next_subscription = self._subscription.effective_at(at, UserSubscription.free(at))
        if next_subscription == self._subscription:
            return False

        self._update_at(at)
        old_subscription = self._subscription
        self._subscription = next_subscription
        self._record_event(
            UserSubscriptionExpired(
                user_id=self._id,
                occurred_at=at,
                old_subscription=old_subscription,
                new_subscription=next_subscription,
            )
        )
        return True

    def mark_seen_at(self, *, at: AwareDatetime) -> bool:
        at = AwareDatetime.ensure(at)
        if at < self._last_seen_at:
            raise ValidationError("at must be >= last_seen_at")
        if at == self._last_seen_at:
            return False

        self._update_at(at)
        self._last_seen_at = at
        return True

    def _assert_management_allowed(
        self, *, actor: UserRole, action: ChangeRole | ChangeSubscription | ChangeState | ChangeProfile
    ) -> None:
        ctx = ManagementContext(
            actor_role=actor,
            target_role=self._role,
            action=action,
        )
        decision = ManagementAccessPolicy.evaluate(ctx)
        match decision:
            case ManagementAllowed():
                return
            case ManagementDenied():
                raise AccessDeniedError(decision.code)
            case _:
                raise InvalidStateTransitionError("unknown management decision")

    def _update_at(self, at: AwareDatetime) -> None:
        if at < self._updated_at:
            raise ValidationError("at must be >= updated_at")
        self._updated_at = at

    def _record_event(self, event: UserEvent) -> None:
        if not isinstance(event, UserEvent):
            raise ValidationError("event must be a UserEvent")
        self._events.append(event)
