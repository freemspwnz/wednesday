from __future__ import annotations

from dataclasses import dataclass

from ...exceptions import ValidationError
from .tier import SubscriptionTier


@dataclass(frozen=True)
class SubscriptionPlan:
    """Subscription plan."""

    tier: SubscriptionTier
    daily_limit: int
    cooldown_minutes: int

    def __post_init__(self) -> None:
        SubscriptionTier.ensure(self.tier)

        if self.daily_limit < 0:
            raise ValidationError("daily_limit must be >= 0")

        if self.cooldown_minutes < 0:
            raise ValidationError("cooldown_minutes must be >= 0")

    @classmethod
    def free(cls) -> SubscriptionPlan:
        return cls(tier=SubscriptionTier.FREE, daily_limit=3, cooldown_minutes=5)

    @classmethod
    def premium(cls) -> SubscriptionPlan:
        return cls(tier=SubscriptionTier.PREMIUM, daily_limit=10, cooldown_minutes=1)

    @classmethod
    def ensure(cls, plan: SubscriptionPlan) -> SubscriptionPlan:
        if not isinstance(plan, cls):
            raise ValidationError("plan must be a SubscriptionPlan")
        return plan
