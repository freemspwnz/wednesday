"""Subscription plan fixtures aligned with catalog/subscriptions.yaml."""

from domain.catalog import SubscriptionPlan, SubscriptionTier

FREE_PLAN: SubscriptionPlan = SubscriptionPlan(
    tier=SubscriptionTier.FREE,
    daily_limit=3,
    cooldown_minutes=3,
)

PREMIUM_PLAN: SubscriptionPlan = SubscriptionPlan(
    tier=SubscriptionTier.PREMIUM,
    daily_limit=10,
    cooldown_minutes=1,
)
