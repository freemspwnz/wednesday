"""Shared helpers for user use-case tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from app.use_cases.user import (
    UserGenerationUseCase,
    UserLifecycleUseCase,
    UserManagementUseCase,
    UserModerationUseCase,
)
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.protocols import UsageRepo, ViolationRepo
from tests.dom.user.factories import (
    FakeModelCatalog,
    FakeSubscriptionCatalog,
    FakeUsageRepo,
    default_settings,
    subscription_free,
)

from ...factories import FakeCacheRegistry, FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def mk_user(*, user_id: int = 1, role: UserRole = UserRole.USER, now: AwareDatetime | None = None) -> User:
    current = now or dt(12)
    return User.register(
        id=UserId(UUID(int=user_id)),
        profile=UserProfile(telegram_id=100_000 + user_id, is_bot=False, first_name=NonEmptyStr("Test")),
        role=role,
        subscription=subscription_free(current),
        settings=default_settings(),
        at=current,
    )


def profile(*, tg_id: int = 999, first_name: str = "A") -> UserProfile:
    return UserProfile(telegram_id=tg_id, is_bot=False, first_name=NonEmptyStr(first_name))


def make_lifecycle_uc(
    *,
    repo: AsyncMock,
    cache_registry: FakeCacheRegistry | None = None,
    logger: Mock | None = None,
) -> tuple[UserLifecycleUseCase, FakeUoW, FakeCacheRegistry]:
    log = logger or mk_logger()
    uow = FakeUoW(users=repo)
    cache = cache_registry or FakeCacheRegistry()
    uc = UserLifecycleUseCase(
        uow=uow,
        cache=cache.users,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        logger=log,
    )
    return uc, uow, cache


def make_management_uc(
    *,
    repo: AsyncMock,
    cache_registry: FakeCacheRegistry | None = None,
) -> tuple[UserManagementUseCase, FakeUoW, FakeCacheRegistry]:
    log = mk_logger()
    uow = FakeUoW(users=repo)
    cache = cache_registry or FakeCacheRegistry()
    uc = UserManagementUseCase(
        uow=uow,
        cache=cache.users,
        logger=log,
    )
    return uc, uow, cache


def make_moderation_uc(
    *,
    repo: AsyncMock | object,
    violations: ViolationRepo | AsyncMock | None = None,
    cache_registry: FakeCacheRegistry | None = None,
    logger: Mock | None = None,
) -> tuple[UserModerationUseCase, FakeUoW, FakeCacheRegistry]:
    log = logger or mk_logger()
    uow = FakeUoW(users=repo, violations=violations)  # type: ignore[arg-type]
    cache = cache_registry or FakeCacheRegistry()
    uc = UserModerationUseCase(
        uow=uow,
        cache=cache.users,
        logger=log,
    )
    return uc, uow, cache


def make_generation_uc(
    *,
    repo: AsyncMock | object,
    usage: UsageRepo | AsyncMock | None = None,
    cache_registry: FakeCacheRegistry | None = None,
) -> tuple[UserGenerationUseCase, FakeUoW, FakeCacheRegistry]:
    log = mk_logger()
    uow = FakeUoW(users=repo, usage=usage or FakeUsageRepo())  # type: ignore[arg-type]
    cache = cache_registry or FakeCacheRegistry()
    uc = UserGenerationUseCase(
        uow=uow,
        cache=cache.users,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        logger=log,
    )
    return uc, uow, cache
