from datetime import timedelta

from .vo import (
    AwareDatetime,
    CooldownViolation,
    DailyLimitViolation,
    LimitAllowed,
    LimitDecision,
    LimitDenied,
    LimitViolation,
    SubscriptionPlan,
    UsageStats,
)


class LimitPolicy:
    """Domain limit policy."""

    @classmethod
    def evaluate(
        cls,
        subscription: SubscriptionPlan,
        stats: UsageStats,
        now: AwareDatetime,
    ) -> LimitDecision:
        """
        Evaluates the limit policy.
        First checks if the daily usage exceeds the limit.
        Then checks if the cooldown period has passed since the last usage.
        If both are satisfied, allows the request.
        If not, denies the request.
        """

        limit = subscription.daily_limit
        cooldown = subscription.cooldown_minutes
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
            remaining = last_usage - now + timedelta(minutes=cooldown)
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
