from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.protocols import ModelRepo
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
class FakeModelRepo:
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
    def ensure(cls, repo: ModelRepo) -> ModelRepo:
        if not isinstance(repo, ModelRepo):
            raise TypeError("repo must be a ModelRepo")
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
