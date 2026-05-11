"""Тесты UserCommandService и UserCommandsUseCase."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from app.exceptions import UserNotFoundError
from app.services.user_commands_srv import UserCommandService
from app.use_cases.user_commands_uc import UserCommandsUseCase
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import (
    ActiveState,
    ManagementAccessDeniedError,
    StaleWriteError,
    SubscriptionPlan,
    User,
    UserId,
    UserProfile,
    UserRole,
    UserSubscription,
    UserSubscriptionExpired,
)
from domain.user.exceptions import InvalidStateTransitionError


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def mk_user(*, user_id: int = 1, role: UserRole = UserRole.USER, now: AwareDatetime | None = None) -> User:
    current = now or dt(12)
    return User.register(
        id=UserId(UUID(int=user_id)),
        profile=UserProfile(telegram_id=100_000 + user_id, is_bot=False, first_name=NonEmptyStr("Test")),
        role=role,
        subscription=UserSubscription.free(current),
        now=current,
    )


def _logger() -> Mock:
    log = Mock()
    log.bind.return_value = log
    return log


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_change_role_persists_via_repo() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    srv = UserCommandService(logger=_logger())

    await srv.change_role(
        repo=repo,
        user_id=user.id,
        actor=UserRole.OWNER,
        new_role=UserRole.ADMIN,
        at=dt(11),
    )

    repo.save.assert_awaited_once_with(user)


class _FakeUoW:
    def __init__(self, users_repo: AsyncMock) -> None:
        self.users = users_repo
        self.chats = AsyncMock()
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self) -> _FakeUoW:
        self.enter_count += 1
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.exit_count += 1


def _make_uc(*, repo: AsyncMock) -> tuple[UserCommandsUseCase, _FakeUoW]:
    log = _logger()
    uow = _FakeUoW(repo)
    uc = UserCommandsUseCase(
        uow=uow,
        user_commands=UserCommandService(logger=log),
        logger=log,
    )
    return uc, uow


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_happy_path_persists_and_closes_uow() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, uow = _make_uc(repo=repo)

    got = await uc.change_role(user_id=user.id, actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(11))

    assert got.role == UserRole.ADMIN
    repo.get_by_id.assert_awaited_once_with(user.id)
    repo.save.assert_awaited_once_with(user)
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_user_not_found_does_not_save() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    uc, uow = _make_uc(repo=repo)
    uid = UserId(UUID(int=99))

    with pytest.raises(UserNotFoundError) as ei:
        await uc.mark_seen(user_id=uid, at=dt(12))

    assert ei.value.user_id == uid
    repo.save.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_management_access_denied_propagates_and_skips_save() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _uow = _make_uc(repo=repo)

    with pytest.raises(ManagementAccessDeniedError):
        await uc.change_role(user_id=user.id, actor=UserRole.USER, new_role=UserRole.ADMIN, at=dt(11))

    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_profile_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _ = _make_uc(repo=repo)
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
    uc, _ = _make_uc(repo=repo)
    new_sub = UserSubscription.premium(dt(11))

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
    uc, _ = _make_uc(repo=repo)

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
    uc, _ = _make_uc(repo=repo)

    await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(11), at=dt(10))
    await uc.change_subscription(
        user_id=user.id,
        actor=UserRole.ADMIN,
        new_subscription=UserSubscription(
            plan=SubscriptionPlan.premium(),
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
    uc, _ = _make_uc(repo=repo)

    await uc.mark_seen(user_id=user.id, at=dt(15))

    assert user.last_seen_at == dt(15)
    repo.save.assert_awaited_once_with(user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_mark_seen_stale_write_propagates() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _ = _make_uc(repo=repo)

    with pytest.raises(StaleWriteError):
        await uc.mark_seen(user_id=user.id, at=dt(9))

    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_unban_active_propagates_invalid_transition() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _ = _make_uc(repo=repo)

    with pytest.raises(InvalidStateTransitionError):
        await uc.unban(user_id=user.id, actor=UserRole.OWNER, at=dt(11))

    repo.save.assert_not_awaited()
