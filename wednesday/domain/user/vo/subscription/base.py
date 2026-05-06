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
        if not isinstance(self.plan, SubscriptionPlan):
            raise ValidationError("plan must be a SubscriptionPlan")
        if not isinstance(self.started_at, AwareDatetime):
            raise ValidationError("started_at must be a AwareDatetime")
        if self.expires_at is not None:
            if not isinstance(self.expires_at, AwareDatetime):
                raise ValidationError("expires_at must be a AwareDatetime")
            if self.started_at >= self.expires_at:
                raise ValidationError("started_at must be before expires_at")

    def is_active_at(self, now: AwareDatetime) -> bool:
        if self.expires_at is None:
            return True
        return self.started_at <= now < self.expires_at

    def effective_at(
        self,
        now: AwareDatetime,
        fallback: UserSubscription,
    ) -> UserSubscription:
        if self.is_active_at(now):
            return self
        return fallback

    @classmethod
    def free(cls, now: AwareDatetime) -> UserSubscription:
        return cls(plan=SubscriptionPlan.free(), started_at=now, expires_at=None)

    @classmethod
    def premium(cls, now: AwareDatetime) -> UserSubscription:
        return cls(plan=SubscriptionPlan.premium(), started_at=now, expires_at=now + timedelta(days=30))
