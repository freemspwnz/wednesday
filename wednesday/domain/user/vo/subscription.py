from __future__ import annotations

from dataclasses import dataclass

from ...catalog.subscription import SubscriptionPlan
from ...kernel.vo import AwareDatetime
from ..exceptions import ValidationError


@dataclass(frozen=True)
class UserSubscription:
    """Value Object: user subscription."""

    plan: SubscriptionPlan
    started_at: AwareDatetime
    expires_at: AwareDatetime | None = None  # None = infinite subscription (free)

    def __post_init__(self) -> None:
        SubscriptionPlan.ensure(self.plan)
        AwareDatetime.ensure(self.started_at)
        if self.expires_at is not None:
            AwareDatetime.ensure(self.expires_at)
            if self.started_at >= self.expires_at:
                raise ValidationError("started_at must be before expires_at")

    def is_active_at(self, at: AwareDatetime) -> bool:
        if self.expires_at is None:
            return True
        return self.started_at <= at < self.expires_at

    def effective_at(
        self,
        fallback: SubscriptionPlan,
        at: AwareDatetime,
    ) -> UserSubscription:
        if self.is_active_at(at):
            return self
        return UserSubscription(
            plan=fallback,
            started_at=self.expires_at or at,
            expires_at=None,
        )

    @classmethod
    def ensure(cls, subscription: UserSubscription) -> UserSubscription:
        if not isinstance(subscription, cls):
            raise ValidationError("subscription must be a UserSubscription")
        return subscription
