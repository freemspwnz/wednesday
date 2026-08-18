"""Tests for UserLifecycleUseCase."""

from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.dto import UserContext
from domain.catalog import SubscriptionPlan, SubscriptionTier
from domain.user import (
    ActiveState,
    StaleWriteError,
    User,
    UserId,
    UserNotFoundError,
    UserRole,
    UserSubscription,
    UserSubscriptionExpired,
)
from tests.dom.user.factories import default_settings, subscription_free

from ...factories import mk_logger, mk_user_context
from .helpers import dt, make_lifecycle_uc, make_management_uc, make_moderation_uc, mk_user, profile


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_loads_and_caches() -> None:
    repo = AsyncMock()
    uc, _, cache = make_lifecycle_uc(repo=repo)
    user_profile = profile(tg_id=42)
    cache.users.get_by_id.return_value = None
    domain_user = User.register(
        id=UserId(UUID(int=7)),
        profile=user_profile,
        role=UserRole.USER,
        subscription=subscription_free(dt(10)),
        settings=default_settings(),
        at=dt(10),
    )

    repo.get_by_id.return_value = domain_user
    got = await uc.register(profile=user_profile)

    assert isinstance(got, UserContext)
    assert got.tg_id == 42
    cache.users.set.assert_awaited_once_with(domain_user)
    repo.save.assert_awaited_once_with(domain_user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_returns_cached_value_without_uow() -> None:
    repo = AsyncMock()
    uc, uow, cache = make_lifecycle_uc(repo=repo)
    user_profile = profile(tg_id=42)
    cached = mk_user_context(user_id=42)
    cache.users.get_by_id.return_value = cached

    got = await uc.register(profile=user_profile)

    assert got is cached
    assert uow.enter_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_logs_info_on_first_create() -> None:
    log = mk_logger()
    repo = AsyncMock()
    uc, _, cache = make_lifecycle_uc(repo=repo, logger=log)
    user_profile = profile(tg_id=42)
    cache.users.get_by_id.return_value = None
    repo.get_by_id.return_value = None

    got = await uc.register(profile=user_profile)

    assert got.tg_id == 42
    log.info.assert_called_once_with("User registered", tg_id=42)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_skips_info_for_existing_user() -> None:
    log = mk_logger()
    repo = AsyncMock()
    uc, _, cache = make_lifecycle_uc(repo=repo, logger=log)
    user_profile = profile(tg_id=42)
    cache.users.get_by_id.return_value = None
    domain_user = mk_user(user_id=42, now=dt(10))
    repo.get_by_id.return_value = domain_user

    await uc.register(profile=user_profile)

    log.info.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_by_tg_id_loads_from_db_without_create() -> None:
    repo = AsyncMock()
    uc, _, cache = make_lifecycle_uc(repo=repo)
    cache.users.get_by_id.return_value = None
    domain_user = mk_user(user_id=8, now=dt(10))

    repo.get_by_id.return_value = domain_user
    got = await uc.find_by_tg_id(tg_id=domain_user.profile.telegram_id)

    assert isinstance(got, UserContext)
    repo.get_by_id.assert_awaited_once()
    cache.users.set.assert_awaited_once_with(domain_user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_by_tg_id_returns_none_without_create() -> None:
    repo = AsyncMock()
    uc, _, cache = make_lifecycle_uc(repo=repo)
    cache.users.get_by_id.return_value = None

    repo.get_by_id.return_value = None
    got = await uc.find_by_tg_id(tg_id=404)

    assert got is None
    repo.get_by_id.assert_awaited_once()
    cache.users.set.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_user_not_found_does_not_save() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    uc, uow, cache = make_lifecycle_uc(repo=repo)
    uid = UserId(UUID(int=99))

    with pytest.raises(UserNotFoundError) as ei:
        await uc.mark_seen(user_id=uid, at=dt(12))

    assert ei.value.user_id == str(uid)
    repo.save.assert_not_awaited()
    cache.users.set.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_expire_ban_and_subscription_emit_domain_events() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    moderation_uc, _, _ = make_moderation_uc(repo=repo)
    management_uc, _, _ = make_management_uc(repo=repo)
    lifecycle_uc, _, _ = make_lifecycle_uc(repo=repo)

    await moderation_uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(11), at=dt(10))
    await management_uc.change_subscription(
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

    await moderation_uc.expire_ban_if_due(user_id=user.id, at=dt(12))
    await lifecycle_uc.expire_subscription_if_due(user_id=user.id, at=dt(10) + timedelta(days=2))

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
    uc, _, _ = make_lifecycle_uc(repo=repo)

    await uc.mark_seen(user_id=user.id, at=dt(15))

    assert user.last_seen_at == dt(15)
    repo.save.assert_awaited_once_with(user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_mark_seen_stale_write_propagates() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = make_lifecycle_uc(repo=repo)

    with pytest.raises(StaleWriteError):
        await uc.mark_seen(user_id=user.id, at=dt(9))
    cache.users.set.assert_not_awaited()
    repo.save.assert_not_awaited()
