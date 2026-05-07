from __future__ import annotations

from enum import IntEnum

from ...exceptions import ValidationError


class SubscriptionTier(IntEnum):
    FREE = 0
    PREMIUM = 1

    @classmethod
    def ensure(cls, tier: SubscriptionTier) -> SubscriptionTier:
        if not isinstance(tier, cls):
            raise ValidationError("tier must be a SubscriptionTier")
        return tier
