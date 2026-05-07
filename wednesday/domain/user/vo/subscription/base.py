from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from ....kernel.vo import AwareDatetime
from ...exceptions import ValidationError
from .plan import SubscriptionPlan


@dataclass(frozen=True)
class UserSubscription:
    plan: SubscriptionPlan
    started_at: AwareDatetime
    expires_at: AwareDatetime | None  # None = бессрочная

    def __post_init__(self) -> None:
        SubscriptionPlan.ensure(self.plan)
        AwareDatetime.ensure(self.started_at)
        if self.expires_at is not None:
            AwareDatetime.ensure(self.expires_at)
            if self.started_at >= self.expires_at:
                raise ValidationError("started_at must be before expires_at")

    def is_active_at(self, now: AwareDatetime) -> bool:
        if self.expires_at is None:
            return True
        return self.started_at <= now < self.expires_at

    def effective_at(
        self,
        now: AwareDatetime,
    ) -> UserSubscription:
        if self.is_active_at(now):
            return self
        if self.expires_at is None:
            return UserSubscription.free(now)
        return UserSubscription.free(self.expires_at)

    @classmethod
    def free(cls, now: AwareDatetime) -> UserSubscription:
        return cls(plan=SubscriptionPlan.free(), started_at=now, expires_at=None)

    @classmethod
    def premium(cls, now: AwareDatetime) -> UserSubscription:
        return cls(plan=SubscriptionPlan.premium(), started_at=now, expires_at=now + timedelta(days=30))

    @classmethod
    def ensure(cls, subscription: UserSubscription) -> UserSubscription:
        if not isinstance(subscription, cls):
            raise ValidationError("subscription must be a UserSubscription")
        return subscription
