from __future__ import annotations

from dataclasses import dataclass, field

from .events import (
    SubscriptionChanged,
    UserBanExpired,
    UserBanned,
    UserEvent,
    UserRoleChanged,
    UserUnbanned,
)
from .exceptions import (
    AccessDeniedError,
    LimitViolationError,
    UserBannedError,
    UserNotBannedError,
    ValidationError,
)
from .policies import (
    BanAssigned,
    BanDurationPolicy,
    LimitAllowed,
    LimitDenied,
    LimitPolicy,
    ManagementAccessAllowed,
    ManagementAccessContext,
    ManagementAccessDenied,
    ManagementAccessPolicy,
    NoBan,
    UsageStats,
    ViolationStats,
)
from .vo import (
    ActiveState,
    AwareDatetime,
    SubscriptionPlan,
    UserProfile,
    UserRole,
    UserState,
    UserTelegramId,
)


@dataclass(slots=True, eq=False)
class User:
    """Aggregate Root: Telegram user.

    Manages its lifecycle: bans, activity,
    identification, subscription.
    """

    _id: UserTelegramId
    _profile: UserProfile
    _role: UserRole
    _subscription: SubscriptionPlan
    _events: list[UserEvent]
    _state: UserState

    _last_seen_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)
    _updated_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)
    _created_at: AwareDatetime = field(default_factory=AwareDatetime.now_utc)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UserTelegramId):
            raise ValidationError("id must be a UserTelegramId")

        if not isinstance(self.subscription, SubscriptionPlan):
            raise ValidationError("subscription must be a SubscriptionPlan")

        if not isinstance(self.profile, UserProfile):
            raise ValidationError("profile must be a UserProfile")

        if not isinstance(self.role, UserRole):
            raise ValidationError("role must be a UserRole")

        if not isinstance(self.state, UserState):
            raise ValidationError("state must be a UserState")

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
        subscription: SubscriptionPlan,
        now: AwareDatetime,
    ) -> User:
        return cls(
            _id=id,
            _profile=profile,
            _role=role,
            _subscription=subscription,
            _events=[],
            _state=ActiveState(),
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
        subscription: SubscriptionPlan,
        state: UserState,
        created_at: AwareDatetime,
        updated_at: AwareDatetime,
        last_seen_at: AwareDatetime,
    ) -> User:
        return cls(
            _id=id,
            _profile=profile,
            _role=role,
            _subscription=subscription,
            _events=[],
            _state=state,
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
    def subscription(self) -> SubscriptionPlan:
        return self._subscription

    @property
    def state(self) -> UserState:
        return self._state

    @property
    def last_seen_at(self) -> AwareDatetime:
        return self._last_seen_at

    @property
    def updated_at(self) -> AwareDatetime:
        return self._updated_at

    @property
    def created_at(self) -> AwareDatetime:
        return self._created_at

    # -- Events --

    def pull_events(self) -> list[UserEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def _record_event(self, event: UserEvent) -> None:
        self._events.append(event)

    # -- Subscription --

    def change_subscription(self, new_plan: SubscriptionPlan, now: AwareDatetime) -> None:
        if not isinstance(new_plan, SubscriptionPlan):
            raise ValidationError("new_plan must be a SubscriptionPlan")

        if self._subscription == new_plan:
            return

        self._ensure_aware(now)
        self._update_at(now)
        old_plan = self._subscription
        self._subscription = new_plan
        self._record_event(
            SubscriptionChanged(
                user_id=self.id,
                occurred_at=now,
                old_plan=old_plan,
                new_plan=new_plan,
            )
        )

    # -- Generation --

    def ensure_can_generate(self, stats: UsageStats, now: AwareDatetime) -> None:
        self._ensure_not_banned(now)
        self._ensure_aware(now)

        if not isinstance(stats, UsageStats):
            raise ValidationError("stats must be a UsageStats")

        stats.validate(now)

        decision = LimitPolicy.evaluate(
            subscription=self.subscription,
            stats=stats,
            now=now,
        )

        match decision:
            case LimitAllowed():
                return
            case LimitDenied():
                raise LimitViolationError(decision.violation)

    # -- Roles --

    def change_role(
        self,
        actor: UserRole,
        new_role: UserRole,
        now: AwareDatetime,
    ) -> None:
        if not isinstance(actor, UserRole):
            raise ValidationError("actor must be a UserRole")

        self._ensure_can_manage(actor)

        if not isinstance(new_role, UserRole):
            raise ValidationError("new_role must be a UserRole")

        self._ensure_different_roles(new_role)
        self._role.ensure_transition_allowed(new_role)
        self._ensure_aware(now)
        self._update_at(now)
        old_role = self._role
        self._role = new_role
        self._record_event(
            UserRoleChanged(
                user_id=self.id,
                occurred_at=now,
                old_role=old_role,
                new_role=new_role,
            )
        )

    def _ensure_different_roles(self, new_role: UserRole) -> None:
        if self._role == new_role:
            raise ValidationError("new_role must be different from the current role")

    # -- State --

    def refresh_state(self, now: AwareDatetime) -> None:
        self._ensure_aware(now)

        new_state = self._state.refresh(now)
        if new_state != self._state:
            self._update_at(now)
            self._state = new_state

            match self._state:
                case ActiveState():
                    self._record_event(
                        UserBanExpired(
                            user_id=self.id,
                            occurred_at=now,
                        )
                    )
                case _:
                    return

    def apply_manual_ban(
        self,
        actor: UserRole,
        until: AwareDatetime,
        now: AwareDatetime,
    ) -> None:
        self._ensure_can_manage(actor)
        self._ensure_aware(now)
        self._ensure_aware(until)
        self._apply_ban(actor, until, now)

    def apply_policy_ban(
        self,
        stats: ViolationStats,
        now: AwareDatetime,
    ) -> None:
        if not isinstance(stats, ViolationStats):
            raise ValidationError("stats must be a ViolationStats")

        self._ensure_aware(now)

        decision = BanDurationPolicy.evaluate(
            stats=stats,
            now=now,
        )

        match decision:
            case BanAssigned(banned_until=until):
                self._apply_ban(UserRole.SYSTEM, until, now)
            case NoBan():
                return

    def _apply_ban(
        self,
        actor: UserRole,
        until: AwareDatetime,
        now: AwareDatetime,
    ) -> None:
        self._update_at(now)
        self._state = self._state.ban_until(until, now)
        self._record_event(
            UserBanned(
                user_id=self.id,
                occurred_at=now,
                until=until,
                actor=actor,
            )
        )

    def unban(
        self,
        actor: UserRole,
        now: AwareDatetime,
    ) -> None:
        self._ensure_can_manage(actor)
        self._ensure_aware(now)
        self._ensure_banned(now)
        self._update_at(now)
        self._state = self._state.unban()
        self._record_event(
            UserUnbanned(
                user_id=self.id,
                occurred_at=now,
                actor=actor,
            )
        )

    def _ensure_not_banned(self, now: AwareDatetime) -> None:
        if self._state.is_banned_at(now):
            raise UserBannedError(f"User {self.id} is banned")

    def _ensure_banned(self, now: AwareDatetime) -> None:
        if not self._state.is_banned_at(now):
            raise UserNotBannedError(f"User {self.id} is not banned")

    # -- Access --

    def _ensure_can_manage(
        self,
        actor: UserRole,
    ) -> None:
        ctx = ManagementAccessContext(actor_role=actor, target_role=self._role)
        decision = ManagementAccessPolicy.evaluate(ctx)

        match decision:
            case ManagementAccessAllowed():
                return
            case ManagementAccessDenied():
                raise AccessDeniedError(decision.code)

    # -- Timestamps --

    def mark_seen_at(self, now: AwareDatetime) -> None:
        self._ensure_aware(now)

        if now < self._last_seen_at:
            raise ValidationError("now must be >= last_seen_at")

        self._update_at(now)
        self._last_seen_at = now

    def _update_at(self, now: AwareDatetime) -> None:
        if now < self._updated_at:
            raise ValidationError("now must be >= updated_at")

        self._updated_at = now

    @staticmethod
    def _ensure_aware(dt: AwareDatetime) -> None:
        if not isinstance(dt, AwareDatetime):
            raise ValidationError("dt must be an AwareDatetime")
