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
from .exceptions import (
    ManagementAccessDeniedError,
    StaleWriteError,
    ValidationError,
)
from .policies import (
    Ban,
    ChangeProfile,
    ChangeRole,
    ChangeSubscription,
    ManagementAccessPolicy,
    ManagementAction,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
    Unban,
)
from .vo import ActiveState, AwareDatetime, UserId, UserProfile, UserRole, UserState, UserSubscription


@dataclass(slots=True, eq=False)  # noqa: PLR0904
class User:
    _id: UserId
    _profile: UserProfile
    _role: UserRole
    _state: UserState
    _subscription: UserSubscription
    _created_at: AwareDatetime
    _updated_at: AwareDatetime
    _last_seen_at: AwareDatetime
    _events: list[UserEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate()

    @classmethod
    def register(
        cls,
        *,
        id: UserId,
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
            _created_at=now,
            _updated_at=now,
            _last_seen_at=now,
        )

    @classmethod
    def restore(  # noqa: PLR0913
        cls,
        *,
        id: UserId,
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
            _created_at=created_at,
            _updated_at=updated_at,
            _last_seen_at=last_seen_at,
        )

    @classmethod
    def ensure(cls, user: User) -> User:
        if not isinstance(user, User):
            raise ValidationError("user must be a User")
        return user

    @property
    def id(self) -> UserId:
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
    ) -> None:
        actor = UserRole.ensure(actor)
        new_role = UserRole.ensure(new_role)
        at = AwareDatetime.ensure(at)

        action = ChangeRole(old_role=self._role, new_role=new_role)
        self._ensure_management_allowed(actor=actor, action=action)
        if new_role != self._role:
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

    def change_profile(
        self,
        *,
        actor: UserRole,
        new_profile: UserProfile,
        at: AwareDatetime,
    ) -> None:
        actor = UserRole.ensure(actor)
        new_profile = UserProfile.ensure(new_profile)
        at = AwareDatetime.ensure(at)

        action = ChangeProfile(old_profile=self._profile, new_profile=new_profile)
        self._ensure_management_allowed(actor=actor, action=action)
        if new_profile != self._profile:
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

    def change_subscription(
        self,
        *,
        actor: UserRole,
        new_subscription: UserSubscription,
        at: AwareDatetime,
    ) -> None:
        actor = UserRole.ensure(actor)
        new_subscription = UserSubscription.ensure(new_subscription)
        at = AwareDatetime.ensure(at)

        action = ChangeSubscription(
            old_subscription=self._subscription,
            new_subscription=new_subscription,
        )
        self._ensure_management_allowed(actor=actor, action=action)
        if new_subscription != self._subscription:
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

    def ban(
        self,
        *,
        actor: UserRole,
        until: AwareDatetime,
        at: AwareDatetime,
    ) -> None:
        actor = UserRole.ensure(actor)
        until = AwareDatetime.ensure(until)
        at = AwareDatetime.ensure(at)

        action = Ban(old_state=self._state, until=until)
        self._ensure_management_allowed(actor=actor, action=action)
        new = self._state.ban_until(until, at)
        if new != self._state:
            self._update_at(at)
            self._state = new
            self._record_event(
                UserBanned(
                    user_id=self._id,
                    occurred_at=at,
                    until=until,
                    actor=actor,
                )
            )

    def unban(
        self,
        *,
        actor: UserRole,
        at: AwareDatetime,
    ) -> None:
        actor = UserRole.ensure(actor)
        at = AwareDatetime.ensure(at)

        action = Unban(old_state=self._state)
        self._ensure_management_allowed(actor=actor, action=action)
        new = self._state.unban()
        self._update_at(at)
        self._state = new
        self._record_event(
            UserUnbanned(
                user_id=self._id,
                occurred_at=at,
                actor=actor,
            )
        )

    def expire_ban_if_due(self, *, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        effective = self._state.effective_at(at)
        if effective != self._state:
            self._updated_at = max(self._updated_at, at)
            self._state = effective
            self._record_event(UserBanExpired(user_id=self._id, occurred_at=at))

    def expire_subscription_if_due(self, *, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        effective = self._subscription.effective_at(at)
        if effective != self._subscription:
            self._updated_at = max(self._updated_at, at)
            old = self._subscription
            self._subscription = effective
            self._record_event(
                UserSubscriptionExpired(
                    user_id=self._id,
                    occurred_at=at,
                    old_subscription=old,
                    new_subscription=effective,
                )
            )

    def mark_seen_at(self, *, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        if at < self._last_seen_at:
            raise StaleWriteError("at must be >= last_seen_at")
        if at == self._last_seen_at:
            return

        self._last_seen_at = at

    def _ensure_management_allowed(
        self,
        *,
        actor: UserRole,
        action: ManagementAction,
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
                raise ManagementAccessDeniedError(decision.code.value)
            case _:
                raise ValidationError("unknown management decision")

    def _update_at(self, at: AwareDatetime) -> None:
        if at < self._updated_at:
            raise StaleWriteError("at must be >= updated_at")
        self._updated_at = at

    def _record_event(self, event: UserEvent) -> None:
        if not isinstance(event, UserEvent):
            raise ValidationError("event must be a UserEvent")
        self._events.append(event)

    def _validate(self) -> None:
        UserId.ensure(self._id)
        UserProfile.ensure(self._profile)
        UserRole.ensure(self._role)
        UserState.ensure(self._state)
        UserSubscription.ensure(self._subscription)
        if not isinstance(self._events, list):
            raise ValidationError("events must be a list[UserEvent]")
        for event in self._events:
            UserEvent.ensure(event)
        AwareDatetime.ensure(self._created_at)
        AwareDatetime.ensure(self._updated_at)
        AwareDatetime.ensure(self._last_seen_at)
        if self._created_at > self._updated_at:
            raise ValidationError("created_at must be <= updated_at")
        if self._created_at > self._last_seen_at:
            raise ValidationError("created_at must be <= last_seen_at")
