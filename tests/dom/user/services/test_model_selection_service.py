from __future__ import annotations

import pytest

from domain.catalog import Model
from domain.user import ModelNotFoundError, ModelSelectionError, ModelSelectionService, UserNotFoundError, UserRole
from domain.user.exceptions import ValidationError

from ..factories import FakeModelCatalog, FakeSubscriptionCatalog, FakeUserRepo, dt, mk_user, subscription_premium


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_resolves_from_registry() -> None:
    user = mk_user(now=dt(10))
    user.change_subscription(
        actor=UserRole.OWNER,
        new_subscription=subscription_premium(dt(10)),
        at=dt(10),
    )
    user.pull_events()
    user_repo = FakeUserRepo.with_users(user)
    model_catalog = FakeModelCatalog()
    sub_catalog = FakeSubscriptionCatalog()

    result = await ModelSelectionService.select_model(
        user_id=user.id,
        model=Model.parse("gigachat-2-pro"),
        user_repo=user_repo,
        model_catalog=model_catalog,
        sub_catalog=sub_catalog,
        at=dt(11),
    )

    assert result.settings.model == Model.parse("gigachat-2-pro")
    assert result.updated_at == dt(11)
    assert user_repo.users[user.id].settings.model == Model.parse("gigachat-2-pro")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_raises_when_model_missing() -> None:
    user = mk_user(now=dt(10))
    user_repo = FakeUserRepo.with_users(user)
    model_catalog = FakeModelCatalog(entries={})
    sub_catalog = FakeSubscriptionCatalog()

    with pytest.raises(ModelNotFoundError) as exc_info:
        await ModelSelectionService.select_model(
            user_id=user.id,
            model=Model.parse("unknown-model"),
            user_repo=user_repo,
            model_catalog=model_catalog,
            sub_catalog=sub_catalog,
            at=dt(11),
        )
    assert "unknown-model" in exc_info.value.model


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_denies_premium_model_for_free_user() -> None:
    user = mk_user(now=dt(10))
    user_repo = FakeUserRepo.with_users(user)
    model_catalog = FakeModelCatalog()
    sub_catalog = FakeSubscriptionCatalog()

    with pytest.raises(ModelSelectionError):
        await ModelSelectionService.select_model(
            user_id=user.id,
            model=Model.parse("gigachat-2-pro"),
            user_repo=user_repo,
            model_catalog=model_catalog,
            sub_catalog=sub_catalog,
            at=dt(11),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_raises_when_user_missing() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(UserNotFoundError):
        await ModelSelectionService.select_model(
            user_id=user.id,
            model=Model.parse("gigachat-2-lite"),
            user_repo=FakeUserRepo(),
            model_catalog=FakeModelCatalog(),
            sub_catalog=FakeSubscriptionCatalog(),
            at=dt(11),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_validates_user_repo() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(ValidationError):
        await ModelSelectionService.select_model(
            user_id=user.id,
            model=Model.parse("gigachat-2-lite"),
            user_repo="bad",  # type: ignore[arg-type]
            model_catalog=FakeModelCatalog(),
            sub_catalog=FakeSubscriptionCatalog(),
            at=dt(11),
        )
