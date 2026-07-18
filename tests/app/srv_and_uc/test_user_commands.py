"""Tests for UserCommandService and UserCommandsUseCase."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from dom.user.factories import (
    FakeModelCatalog,
    FakeSubscriptionCatalog,
    default_settings,
    subscription_free,
    subscription_premium,
)

from app.exceptions import UserNotFoundError
from app.services.user import UserCommandService
from app.use_cases.user import UserCommandsUseCase
from domain.catalog import SubscriptionPlan, SubscriptionTier
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import (
    AccessDeniedError,
    ActiveState,
    StaleWriteError,
    User,
    UserId,
    UserProfile,
    UserRole,
    UserSubscription,
    UserSubscriptionExpired,
)
from domain.user.exceptions import InvalidStateTransitionError

from ..factories import FakeCacheRegistry, FakeUoW, mk_logger


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


def _user_commands_srv() -> UserCommandService:
    return UserCommandService(
        subscriptions=FakeSubscriptionCatalog(),
        logger=mk_logger(),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_change_role_persists_via_repo() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    srv = _user_commands_srv()

    await srv.change_role(
        repo=repo,
        user_id=user.id,
        actor=UserRole.OWNER,
        new_role=UserRole.ADMIN,
        at=dt(11),
    )

    repo.save.assert_awaited_once_with(user)


def _make_uc(
    *,
    repo: AsyncMock,
    cache_registry: FakeCacheRegistry | None = None,
) -> tuple[UserCommandsUseCase, FakeUoW, FakeCacheRegistry]:
    log = mk_logger()
    uow = FakeUoW(users=repo)
    cache = cache_registry or FakeCacheRegistry()
    uc = UserCommandsUseCase(
        uow=uow,
        service=_user_commands_srv(),
        cache=cache.users,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        logger=log,
    )
    return uc, uow, cache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_happy_path_persists_and_closes_uow() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, uow, cache = _make_uc(repo=repo)

    got = await uc.change_role(user_id=user.id, actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(11))

    assert got.role == UserRole.ADMIN
    repo.get_by_id.assert_awaited_once_with(user.id)
    repo.save.assert_awaited_once_with(user)
    cache.users.set.assert_awaited_once_with(got)
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_user_not_found_does_not_save() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    uc, uow, cache = _make_uc(repo=repo)
    uid = UserId(UUID(int=99))

    with pytest.raises(UserNotFoundError) as ei:
        await uc.mark_seen(user_id=uid, at=dt(12))

    assert ei.value.user_id == uid
    repo.save.assert_not_awaited()
    cache.users.set.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_management_access_denied_propagates_and_skips_save() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _uow, cache = _make_uc(repo=repo)

    with pytest.raises(AccessDeniedError):
        await uc.change_role(user_id=user.id, actor=UserRole.USER, new_role=UserRole.ADMIN, at=dt(11))

    repo.save.assert_not_awaited()
    cache.users.set.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_profile_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, _ = _make_uc(repo=repo)
    new_profile = UserProfile(telegram_id=user.profile.telegram_id, is_bot=False, first_name=NonEmptyStr(" Neo"))

    await uc.change_profile(user_id=user.id, actor=UserRole.SYSTEM, new_profile=new_profile, at=dt(11))

    assert user.profile.first_name == NonEmptyStr(" Neo")
    repo.save.assert_awaited_once_with(user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_subscription_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, _ = _make_uc(repo=repo)
    new_sub = subscription_premium(dt(11))

    await uc.change_subscription(
        user_id=user.id,
        actor=UserRole.ADMIN,
        new_subscription=new_sub,
        at=dt(11),
    )

    assert user.subscription.plan.tier == new_sub.plan.tier
    repo.save.assert_awaited_once_with(user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_ban_and_unban_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, _ = _make_uc(repo=repo)

    await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(20), at=dt(12))
    assert user.state.is_banned_at(dt(15))
    await uc.unban(user_id=user.id, actor=UserRole.OWNER, at=dt(13))
    assert isinstance(user.state, ActiveState)

    assert repo.save.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_expire_ban_and_subscription_emit_domain_events() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, _ = _make_uc(repo=repo)

    await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(11), at=dt(10))
    await uc.change_subscription(
        user_id=user.id,
        actor=UserRole.ADMIN,
        new_subscription=UserSubscription(
            plan=SubscriptionPlan(tier=SubscriptionTier.PREMIUM, daily_limit=10, cooldown_minutes=1),
            started_at=dt(10),
            expires_at=dt(11),
        ),
        at=dt(10),
    )
    user.pull_events()
    repo.save.reset_mock()

    await uc.expire_ban_if_due(user_id=user.id, at=dt(12))
    await uc.expire_subscription_if_due(user_id=user.id, at=dt(10) + timedelta(days=2))

    events = user.pull_events()
    assert any(isinstance(e, UserSubscriptionExpired) for e in events)
    assert isinstance(user.state, ActiveState)
    assert repo.save.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_mark_seen_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, _ = _make_uc(repo=repo)

    await uc.mark_seen(user_id=user.id, at=dt(15))

    assert user.last_seen_at == dt(15)
    repo.save.assert_awaited_once_with(user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_mark_seen_stale_write_propagates() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = _make_uc(repo=repo)

    with pytest.raises(StaleWriteError):
        await uc.mark_seen(user_id=user.id, at=dt(9))
    cache.users.set.assert_not_awaited()
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_unban_active_propagates_invalid_transition() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = _make_uc(repo=repo)

    with pytest.raises(InvalidStateTransitionError):
        await uc.unban(user_id=user.id, actor=UserRole.OWNER, at=dt(11))
    cache.users.set.assert_not_awaited()
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_refreshes_user_cache_snapshot() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, cache = _make_uc(repo=repo)

    got = await uc.change_role(
        user_id=user.id,
        actor=UserRole.OWNER,
        new_role=UserRole.ADMIN,
        at=dt(11),
    )

    cache.users.set.assert_awaited_once_with(got)
    assert got.profile.telegram_id == user.profile.telegram_id
    assert got.role == UserRole.ADMIN


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_ban_refreshes_user_cache_snapshot() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = _make_uc(repo=repo)

    got = await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(20), at=dt(12))

    cache.users.set.assert_awaited_once_with(got)
    assert got.state.is_banned_at(dt(15))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_unban_after_ban_refreshes_cache_twice() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = _make_uc(repo=repo)

    await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(20), at=dt(12))
    await uc.unban(user_id=user.id, actor=UserRole.OWNER, at=dt(13))

    assert cache.users.set.await_count == 2
