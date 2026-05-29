from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from domain.catalog import (
    Model,
    ModelCatalog,
    ModelDescriptor,
    Series,
    SubscriptionCatalog,
    SubscriptionPlan,
    SubscriptionTier,
    Vendor,
)
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.policies import UsageStats, ViolationStats
from domain.user.protocols import UsageRepo, UserRepo, ViolationRepo
from domain.user.vo import UserSettings, UserSubscription

from ..catalog import FREE_PLAN, PREMIUM_PLAN


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def default_settings() -> UserSettings:
    return UserSettings(
        vendor=Vendor.parse("sber"),
        series=Series.parse("gigachat"),
        model=Model.parse("gigachat-2-lite"),
    )


def descriptor_lite(*, active: bool = True) -> ModelDescriptor:
    return ModelDescriptor(
        model=Model.parse("gigachat-2-lite"),
        vendor=Vendor.parse("sber"),
        series=Series.parse("gigachat"),
        display_name="GigaChat 2 Lite",
        min_tier=SubscriptionTier.FREE,
        active=active,
    )


def descriptor_pro(*, active: bool = True) -> ModelDescriptor:
    return ModelDescriptor(
        model=Model.parse("gigachat-2-pro"),
        vendor=Vendor.parse("sber"),
        series=Series.parse("gigachat"),
        display_name="GigaChat 2 Pro",
        min_tier=SubscriptionTier.PREMIUM,
        active=active,
    )


def plan_free() -> SubscriptionPlan:
    return FREE_PLAN


def plan_premium() -> SubscriptionPlan:
    return PREMIUM_PLAN


def subscription_free(now: AwareDatetime, *, expires_at: AwareDatetime | None = None) -> UserSubscription:
    return UserSubscription(plan=plan_free(), started_at=now, expires_at=expires_at)


def subscription_premium(now: AwareDatetime, *, expires_at: AwareDatetime | None = None) -> UserSubscription:
    return UserSubscription(plan=plan_premium(), started_at=now, expires_at=expires_at)


@dataclass
class FakeSubscriptionCatalog(SubscriptionCatalog):
    """In-memory SubscriptionCatalog for domain tests."""

    plans: dict[SubscriptionTier, SubscriptionPlan] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plans:
            self.plans = {
                SubscriptionTier.FREE: plan_free(),
                SubscriptionTier.PREMIUM: plan_premium(),
            }

    async def get_by_tier(self, tier: SubscriptionTier) -> SubscriptionPlan:
        return self.plans[tier]

    async def list_active(self) -> list[SubscriptionPlan]:
        return list(self.plans.values())

    async def default_plan(self) -> SubscriptionPlan:
        return self.plans[SubscriptionTier.FREE]

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, SubscriptionCatalog):
            raise TypeError("repo must be a SubscriptionCatalog")
        return repo


@dataclass
class FakeModelCatalog(ModelCatalog):
    """In-memory ModelCatalog for domain tests."""

    entries: dict[str, ModelDescriptor] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.entries:
            lite = descriptor_lite()
            pro = descriptor_pro()
            self.entries = {
                str(lite.model): lite,
                str(pro.model): pro,
            }

    async def get_by_model(self, model: Model) -> ModelDescriptor | None:
        return self.entries.get(str(model))

    async def list_active(self) -> list[ModelDescriptor]:
        return [entry for entry in self.entries.values() if entry.active]

    async def default_for_tier(self, tier: SubscriptionTier) -> ModelDescriptor:
        if tier == SubscriptionTier.PREMIUM:
            return descriptor_pro()
        return descriptor_lite()

    async def exists(self, model: Model) -> bool:
        return str(model) in self.entries

    async def list_vendors(self) -> list[Vendor]:
        return sorted({entry.vendor for entry in self.entries.values()}, key=str)

    async def list_series(self, vendor: Vendor) -> list[Series]:
        return sorted(
            {entry.series for entry in self.entries.values() if entry.vendor == vendor},
            key=str,
        )

    async def list_models(self, vendor: Vendor, series: Series) -> list[Model]:
        return sorted(
            [entry.model for entry in self.entries.values() if entry.vendor == vendor and entry.series == series],
            key=str,
        )

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, ModelCatalog):
            raise TypeError("repo must be a ModelCatalog")
        return repo


@dataclass
class FakeUserRepo(UserRepo):
    """In-memory UserRepo for domain tests."""

    users: dict[UserId, User] = field(default_factory=dict)

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self.users.get(UserId.ensure(user_id))

    async def save(self, user: User) -> None:
        entity = User.ensure(user)
        self.users[entity.id] = entity

    async def exists(self, user_id: UserId) -> bool:
        return UserId.ensure(user_id) in self.users

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, UserRepo):
            raise TypeError("repo must be a UserRepo")
        return repo

    @classmethod
    def with_users(cls, *users: User) -> FakeUserRepo:
        repo = cls()
        for user in users:
            repo.users[user.id] = user
        return repo


@dataclass
class FakeUsageRepo(UsageRepo):
    """In-memory UsageRepo for domain tests."""

    stats: UsageStats = field(
        default_factory=lambda: UsageStats(last_usage=None, daily_usage=0),
    )

    async def get_usage_stats(self, user_id: UserId) -> UsageStats:
        _ = UserId.ensure(user_id)
        return self.stats

    async def record_usage(self, user_id: UserId, at: AwareDatetime) -> None:
        _ = UserId.ensure(user_id)
        _ = AwareDatetime.ensure(at)
        self.stats = UsageStats(last_usage=at, daily_usage=self.stats.daily_usage + 1)

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, UsageRepo):
            raise TypeError("repo must be a UsageRepo")
        return repo


@dataclass
class FakeViolationRepo(ViolationRepo):
    """In-memory ViolationRepo for domain tests."""

    stats: ViolationStats = field(
        default_factory=lambda: ViolationStats(hour=0, today=0, week=0, total=0),
    )

    async def get_violation_stats(self, user_id: UserId) -> ViolationStats:
        _ = UserId.ensure(user_id)
        return self.stats

    async def record_violation(self, user_id: UserId, at: AwareDatetime) -> None:
        _ = UserId.ensure(user_id)
        _ = AwareDatetime.ensure(at)
        self.stats = ViolationStats(
            hour=self.stats.hour + 1,
            today=self.stats.today + 1,
            week=self.stats.week + 1,
            total=self.stats.total + 1,
        )

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, ViolationRepo):
            raise TypeError("repo must be a ViolationRepo")
        return repo


def mk_user(
    *,
    user_id: int = 1,
    role: UserRole = UserRole.USER,
    now: AwareDatetime | None = None,
    settings: UserSettings | None = None,
) -> User:
    current = now or dt(12)
    return User.register(
        id=UserId(UUID(int=user_id)),
        profile=UserProfile(telegram_id=100_000 + user_id, is_bot=False, first_name=NonEmptyStr("Test")),
        role=role,
        subscription=subscription_free(current),
        settings=settings or default_settings(),
        at=current,
    )
