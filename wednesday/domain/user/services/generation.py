from __future__ import annotations

from ..exceptions import CooldownViolationError, LimitViolationError, UserBannedError, ValidationError
from ..policies import (
    CooldownViolation,
    DailyLimitViolation,
    LimitAllowed,
    LimitDenied,
    LimitPolicy,
    UsageStats,
)
from ..user import User
from ..vo import AwareDatetime


class GenerationAccessService:
    """Проверки перед генерацией: бан, статистика, лимиты по эффективной подписке."""

    @staticmethod
    def assert_generation_allowed(
        user: User,
        stats: UsageStats,
        at: AwareDatetime,
    ) -> None:
        user = User.ensure(user)
        if not isinstance(stats, UsageStats):
            raise ValidationError("stats must be a UsageStats")
        at = AwareDatetime.ensure(at)

        subscription = user.subscription.effective_at(at)
        state = user.state.effective_at(at)
        if state.is_banned_at(at):
            raise UserBannedError("user is banned")

        decision = LimitPolicy.evaluate(
            subscription=subscription,
            stats=stats,
            at=at,
        )

        match decision:
            case LimitAllowed():
                return
            case LimitDenied(violation=v):
                GenerationAccessService._raise_limit_violation(v)
            case _:
                raise ValidationError("unknown limit decision")

    @staticmethod
    def _raise_limit_violation(violation: DailyLimitViolation | CooldownViolation) -> None:
        match violation:
            case DailyLimitViolation():
                raise LimitViolationError(
                    violation.code.value,
                    {"daily_limit": violation.daily_limit, "used": violation.used},
                )
            case CooldownViolation():
                raise CooldownViolationError(
                    violation.code.value,
                    {
                        "cooldown_minutes": violation.cooldown_minutes,
                        "remaining_seconds": int(violation.remaining.total_seconds()),
                    },
                )
            case _:
                raise ValidationError("unknown limit violation")
