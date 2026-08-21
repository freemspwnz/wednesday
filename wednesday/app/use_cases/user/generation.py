from datetime import datetime
from uuid import UUID

from app.dto import UserContext
from app.protocols import CacheRepo, Logger, UoW
from domain.catalog import Model, ModelCatalog, SubscriptionCatalog
from domain.kernel.vo import AwareDatetime
from domain.user import ModelNotFoundError, UsageSnapshot, User, UserBannedError, UserId
from domain.user.exceptions import CooldownViolationError, LimitViolationError, ValidationError
from domain.user.policies import CooldownViolation, DailyLimitViolation, LimitAllowed, LimitDenied, LimitPolicy

from .base import UserBaseUseCase


class UserGenerationUseCase(UserBaseUseCase):
    """User generation use case methods."""

    def __init__(
        self,
        *,
        models: ModelCatalog,
        subscriptions: SubscriptionCatalog,
        uow: UoW,
        cache: CacheRepo[UserContext],
        logger: Logger,
    ) -> None:
        super().__init__(uow=uow, cache=cache, logger=logger)
        self._models = models
        self._subscriptions = subscriptions

    async def list_selectable_models(self, *, subscription_tier: int) -> list[tuple[str, str]]:
        """Active catalog models allowed for the given subscription tier.

        Returns ``(code, display_name)`` pairs sorted by code.
        """
        descriptors = await self._models.list_active()
        allowed = [d for d in descriptors if int(d.min_tier) <= subscription_tier]
        allowed.sort(key=lambda d: str(d.model))
        return [(str(d.model), d.display_name) for d in allowed]

    async def select_model(
        self,
        *,
        user_id: str,
        model: str,
        at: datetime,
    ) -> UserContext:
        return await self._run_mutating(
            action="select_model",
            user_id=user_id,
            runner=lambda: self._select_model(
                user_id=UserId(UUID(user_id)),
                model=Model.parse(model),
                at=AwareDatetime.from_datetime(at),
            ),
        )

    async def begin_generation(self, *, user_id: str, at: datetime) -> UsageSnapshot:
        """Reserve one generation slot after limit checks (check + record in one UoW).

        Returns a snapshot for ``refund_generation`` when render, send, or register fails.
        """
        self._log_scenario_start(action="begin_generation", user_id=user_id)
        time = AwareDatetime.from_datetime(at)
        uid = UserId(UUID(user_id))
        async with self._uow:
            await self._assert_allowed(user_id=uid, at=time)
            return await self._uow.usage.record(uid, time)

    async def refund_generation(self, *, user_id: str, snapshot: UsageSnapshot) -> None:
        """Restore usage counters from a snapshot when generation did not finish successfully."""
        self._log_scenario_start(action="refund_generation", user_id=user_id)
        async with self._uow:
            await self._uow.usage.refund(UserId(UUID(user_id)), snapshot)

    async def _select_model(
        self,
        *,
        user_id: UserId,
        model: Model,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        descriptor = await self._models.get_by_model(model)
        if descriptor is None:
            raise ModelNotFoundError(str(model))

        fallback = await self._subscriptions.default_plan()
        user.change_settings(fallback=fallback, descriptor=descriptor, at=at)
        await self._uow.users.save(user)
        return user

    async def _assert_allowed(self, *, user_id: UserId, at: AwareDatetime) -> None:
        user = await self._load_user_or_raise(user_id=user_id)
        stats = await self._uow.usage.get_stats(user_id, at, True)
        default_plan = await self._subscriptions.default_plan()

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
                return
            case LimitDenied(violation=v):
                self._raise_limit_violation(v)
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
