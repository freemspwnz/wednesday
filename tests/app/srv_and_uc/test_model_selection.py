"""Tests for select_model in UserCommandsUseCase."""

from datetime import UTC, datetime

import pytest
from dom.user.factories import FakeModelCatalog, FakeSubscriptionCatalog, FakeUserRepo, mk_user, subscription_premium

from app.services.user import UserCommandService
from app.use_cases.user import UserCommandsUseCase
from domain.catalog import Model
from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

from ..factories import FakeCacheRegistry, FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_select_model_persists_and_refreshes_cache() -> None:
    user = mk_user(user_id=5, now=dt(10))
    user.change_subscription(
        actor=UserRole.OWNER,
        new_subscription=subscription_premium(dt(10)),
        at=dt(10),
    )
    user.pull_events()
    user_repo = FakeUserRepo.with_users(user)
    cache = FakeCacheRegistry()
    uc = UserCommandsUseCase(
        uow=FakeUoW(users=user_repo),
        service=UserCommandService(
            subscriptions=FakeSubscriptionCatalog(),
            logger=mk_logger(),
        ),
        cache=cache.users,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        logger=mk_logger(),
    )

    got = await uc.select_model(
        user_id=user.id,
        model=Model.parse("gigachat-2-pro"),
        at=dt(11),
    )

    assert got.settings.model == Model.parse("gigachat-2-pro")
    assert user_repo.users[user.id].settings.model == Model.parse("gigachat-2-pro")
    cache.users.set.assert_awaited_once_with(got)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_select_model_closes_uow() -> None:
    user = mk_user(user_id=6, now=dt(10))
    user_repo = FakeUserRepo.with_users(user)
    uow = FakeUoW(users=user_repo)
    cache = FakeCacheRegistry()
    uc = UserCommandsUseCase(
        uow=uow,
        service=UserCommandService(
            subscriptions=FakeSubscriptionCatalog(),
            logger=mk_logger(),
        ),
        cache=cache.users,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        logger=mk_logger(),
    )

    await uc.select_model(
        user_id=user.id,
        model=Model.parse("gigachat-2-lite"),
        at=dt(11),
    )

    assert uow.enter_count == uow.exit_count == 1
