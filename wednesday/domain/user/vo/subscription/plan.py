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
        if not isinstance(self.tier, SubscriptionTier):
            raise ValidationError("tier must be a SubscriptionTier")

        if self.daily_limit < 0:
            raise ValidationError("daily_limit must be >= 0")

        if self.cooldown_minutes < 0:
            raise ValidationError("cooldown_minutes must be >= 0")
