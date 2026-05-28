from __future__ import annotations

from domain.catalog import SubscriptionCatalog

from ..exceptions import CooldownViolationError, LimitViolationError, UserBannedError, ValidationError
from ..policies import (
    CooldownViolation,
    DailyLimitViolation,
    LimitAllowed,
    LimitDenied,
    LimitPolicy,
)
from ..protocols import UsageRepo
from ..user import User
from ..vo import AwareDatetime


class GenerationAccessService:
    """Проверки перед генерацией: бан, статистика, лимиты по эффективной подписке."""

    @staticmethod
    async def assert_generation_allowed(
        user: User,
        repo: UsageRepo,
        catalog: SubscriptionCatalog,
        at: AwareDatetime,
    ) -> None:
        user = User.ensure(user)
        repo = UsageRepo.ensure(repo)
        catalog = SubscriptionCatalog.ensure(catalog)
        at = AwareDatetime.ensure(at)

        stats = await repo.get_usage_stats(user.id)
        default_plan = await catalog.default_plan()

        subscription = user.subscription.effective_at(default_plan, at)
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
                await repo.record_usage(user.id, at)
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
