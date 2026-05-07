from datetime import timedelta

from ...vo import AwareDatetime, UserSubscription
from .vo import (
    CooldownViolation,
    DailyLimitViolation,
    LimitAllowed,
    LimitDecision,
    LimitDenied,
    LimitViolation,
    UsageStats,
)


class LimitPolicy:
    """Domain limit policy."""

    @classmethod
    def evaluate(
        cls,
        subscription: UserSubscription,
        stats: UsageStats,
        at: AwareDatetime,
    ) -> LimitDecision:
        limit = subscription.plan.daily_limit
        cooldown = subscription.plan.cooldown_minutes
        daily_usage = stats.daily_usage
        last_usage = stats.last_usage

        if daily_usage >= limit:
            return cls.deny(
                DailyLimitViolation(
                    daily_limit=limit,
                    used=daily_usage,
                )
            )

        if last_usage is not None:
            remaining = last_usage + timedelta(minutes=cooldown) - at
            if remaining.total_seconds() > 0:
                return cls.deny(
                    CooldownViolation(
                        cooldown_minutes=cooldown,
                        remaining=remaining,
                    )
                )

        return cls.allow()

    @classmethod
    def allow(cls) -> LimitAllowed:
        return LimitAllowed()

    @classmethod
    def deny(cls, violation: LimitViolation) -> LimitDenied:
        return LimitDenied(violation=violation)
