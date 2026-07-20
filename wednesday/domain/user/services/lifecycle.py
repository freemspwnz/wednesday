from domain.catalog import ModelCatalog, SubscriptionCatalog

from ..protocols import UserRepo
from ..user import User
from ..vo import AwareDatetime, UserId, UserProfile, UserRole, UserSettings, UserSubscription
from .utils import load_or_raise, user_id_from_tg


class UserLifecycleService:
    """User identity lifecycle: registration, presence, subscription reconciliation."""

    @staticmethod
    async def get_or_create(
        *,
        profile: UserProfile,
        repo: UserRepo,
        models: ModelCatalog,
        subscriptions: SubscriptionCatalog,
        at: AwareDatetime,
    ) -> User:
        profile = UserProfile.ensure(profile)
        at = AwareDatetime.ensure(at)
        models = ModelCatalog.ensure(models)
        subscriptions = SubscriptionCatalog.ensure(subscriptions)
        user_id = user_id_from_tg(profile.telegram_id)

        existing = await repo.get_by_id(user_id)
        if existing is not None:
            existing.mark_seen_at(at=at)
            await repo.save(existing)
            return existing

        default_plan = await subscriptions.default_plan()
        default_descriptor = await models.default_for_tier(default_plan.tier)
        user = User.register(
            id=user_id,
            profile=profile,
            role=UserRole.USER,
            subscription=UserSubscription(
                plan=default_plan,
                started_at=at,
                expires_at=None,
            ),
            settings=UserSettings.from_descriptor(default_descriptor),
            at=at,
        )
        await repo.save(user)
        return user

    @staticmethod
    async def get_if_exists(*, tg_id: int, repo: UserRepo) -> User | None:
        return await repo.get_by_id(user_id_from_tg(tg_id))

    @staticmethod
    async def expire_subscription_if_due(
        *,
        id: UserId,
        repo: UserRepo,
        subscriptions: SubscriptionCatalog,
        at: AwareDatetime,
    ) -> User:
        id = UserId.ensure(id)
        at = AwareDatetime.ensure(at)
        subscriptions = SubscriptionCatalog.ensure(subscriptions)

        user = await load_or_raise(repo=repo, id=id)
        fallback = await subscriptions.default_plan()
        user.expire_subscription_if_due(fallback=fallback, at=at)
        await repo.save(user)
        return user

    @staticmethod
    async def mark_seen(
        *,
        id: UserId,
        repo: UserRepo,
        at: AwareDatetime,
    ) -> User:
        id = UserId.ensure(id)
        at = AwareDatetime.ensure(at)

        user = await load_or_raise(repo=repo, id=id)
        user.mark_seen_at(at=at)
        await repo.save(user)
        return user
