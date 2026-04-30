from __future__ import annotations

from ..vo import SubscriptionPlan, SubscriptionTier


class SubscriptionCatalog:
    """Каталог подписок."""

    @staticmethod
    def free() -> SubscriptionPlan:
        return SubscriptionPlan(SubscriptionTier.FREE, daily_limit=3, cooldown_minutes=5)

    @staticmethod
    def premium() -> SubscriptionPlan:
        return SubscriptionPlan(SubscriptionTier.PREMIUM, daily_limit=10, cooldown_minutes=1)
