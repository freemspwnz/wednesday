from __future__ import annotations

import pytest

from domain.catalog import Model
from domain.user import UserRole
from domain.user.exceptions import ModelNotFoundError, ModelSelectionError
from domain.user.services.model_selection import ModelSelectionService

from ..factories import FakeModelCatalog, FakeSubscriptionCatalog, dt, mk_user, subscription_premium


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
    model_catalog = FakeModelCatalog()
    sub_catalog = FakeSubscriptionCatalog()

    await ModelSelectionService.select_model(
        user=user,
        model=Model.parse("gigachat-2-pro"),
        model_catalog=model_catalog,
        sub_catalog=sub_catalog,
        at=dt(11),
    )

    assert user.settings.model == Model.parse("gigachat-2-pro")
    assert user.updated_at == dt(11)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_raises_when_model_missing() -> None:
    user = mk_user(now=dt(10))
    model_catalog = FakeModelCatalog(entries={})
    sub_catalog = FakeSubscriptionCatalog()

    with pytest.raises(ModelNotFoundError) as exc_info:
        await ModelSelectionService.select_model(
            user=user,
            model=Model.parse("unknown-model"),
            model_catalog=model_catalog,
            sub_catalog=sub_catalog,
            at=dt(11),
        )
    assert "unknown-model" in exc_info.value.model


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_denies_premium_model_for_free_user() -> None:
    user = mk_user(now=dt(10))
    model_catalog = FakeModelCatalog()
    sub_catalog = FakeSubscriptionCatalog()

    with pytest.raises(ModelSelectionError):
        await ModelSelectionService.select_model(
            user=user,
            model=Model.parse("gigachat-2-pro"),
            model_catalog=model_catalog,
            sub_catalog=sub_catalog,
            at=dt(11),
        )
