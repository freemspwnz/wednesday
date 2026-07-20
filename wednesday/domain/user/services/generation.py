from domain.catalog import Model, ModelCatalog, SubscriptionCatalog

from ..exceptions import (
    CooldownViolationError,
    LimitViolationError,
    ModelNotFoundError,
    UserBannedError,
    UserNotFoundError,
    ValidationError,
)
from ..policies import (
    CooldownViolation,
    DailyLimitViolation,
    LimitAllowed,
    LimitDenied,
    LimitPolicy,
)
from ..protocols import UsageRepo, UserRepo
from ..user import User
from ..vo import AwareDatetime, UserId


class UserGenerationService:
    """User generation settings and pre-generation access checks."""

    @staticmethod
    async def select_model(  # noqa: PLR0913
        *,
        id: UserId,
        model: Model,
        repo: UserRepo,
        models: ModelCatalog,
        subs: SubscriptionCatalog,
        at: AwareDatetime,
    ) -> User:
        id = UserId.ensure(id)
        model = Model.ensure(model)
        at = AwareDatetime.ensure(at)
        if not isinstance(repo, UserRepo):
            raise ValidationError("user_repo must implement UserRepo")
        models = ModelCatalog.ensure(models)
        subs = SubscriptionCatalog.ensure(subs)

        user = await repo.get_by_id(id)
        if user is None:
            raise UserNotFoundError(str(id))

        descriptor = await models.get_by_model(model)
        if descriptor is None:
            raise ModelNotFoundError(str(model))

        fallback = await subs.default_plan()

        user.change_settings(fallback=fallback, descriptor=descriptor, at=at)
        await repo.save(user)
        return user

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
                UserGenerationService._raise_limit_violation(v)
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
