from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.policies import UsageStats, ViolationStats
from domain.user.protocols import ModelRepo, UsageRepo, ViolationRepo
from domain.user.vo import (
    Model,
    ModelDescriptor,
    Series,
    SubscriptionTier,
    UserSettings,
    UserSubscription,
    Vendor,
)


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


@dataclass
class FakeModelRepo(ModelRepo):
    """In-memory ModelRepo for domain tests."""

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

    async def default_for_tier(self, tier: SubscriptionTier) -> Model:
        if tier == SubscriptionTier.PREMIUM:
            return Model.parse("gigachat-2-pro")
        return Model.parse("gigachat-2-lite")

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, ModelRepo):
            raise TypeError("repo must be a ModelRepo")
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
        subscription=UserSubscription.free(current),
        settings=settings or default_settings(),
        at=current,
    )
