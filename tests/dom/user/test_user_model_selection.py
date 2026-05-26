from __future__ import annotations

import pytest

from domain.user import User, UserRole, UserSubscription
from domain.user.events import UserSettingsChanged
from domain.user.exceptions import ModelNotFoundError, ModelSelectionError, ValidationError
from domain.user.policies.model_selection import (
    ModelSelectionAllowed,
    ModelSelectionCode,
    ModelSelectionDenied,
    ModelSelectionPolicy,
)
from domain.user.services.model_selection import ModelSelectionService
from domain.user.vo import Model, ModelDescriptor, Series, SubscriptionTier, UserSettings, Vendor

from .factories import (
    FakeModelRepo,
    default_settings,
    descriptor_lite,
    descriptor_pro,
    dt,
    mk_user,
)


@pytest.mark.unit
def test_model_selection_policy_allows_free_tier_for_lite() -> None:
    decision = ModelSelectionPolicy.evaluate(
        subscription=UserSubscription.free(dt(10)),
        descriptor=descriptor_lite(),
        at=dt(10),
    )
    assert isinstance(decision, ModelSelectionAllowed)


@pytest.mark.unit
def test_model_selection_policy_denies_premium_model_on_free() -> None:
    decision = ModelSelectionPolicy.evaluate(
        subscription=UserSubscription.free(dt(10)),
        descriptor=descriptor_pro(),
        at=dt(10),
    )
    assert isinstance(decision, ModelSelectionDenied)
    assert decision.code == ModelSelectionCode.TIER_TOO_LOW


@pytest.mark.unit
def test_model_selection_policy_denies_inactive_model() -> None:
    decision = ModelSelectionPolicy.evaluate(
        subscription=UserSubscription.premium(dt(10)),
        descriptor=descriptor_pro(active=False),
        at=dt(10),
    )
    assert isinstance(decision, ModelSelectionDenied)
    assert decision.code == ModelSelectionCode.MODEL_NOT_ACTIVE


@pytest.mark.unit
def test_model_descriptor_and_settings_from_descriptor_validate() -> None:
    descriptor = descriptor_lite()
    settings = UserSettings.from_descriptor(descriptor)
    assert settings.model == descriptor.model
    assert settings.vendor == descriptor.vendor
    assert settings.series == descriptor.series

    with pytest.raises(ValidationError):
        ModelDescriptor(
            model=Model.parse("gigachat-2-lite"),
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            display_name=" ",
            min_tier=SubscriptionTier.FREE,
        )


@pytest.mark.unit
def test_change_settings_updates_state_and_emits_event() -> None:
    user = mk_user(now=dt(10))
    user.change_subscription(
        actor=UserRole.OWNER,
        new_subscription=UserSubscription.premium(dt(10)),
        at=dt(10),
    )
    user.pull_events()

    user.change_settings(descriptor=descriptor_pro(), at=dt(11))

    assert user.settings.model == Model.parse("gigachat-2-pro")
    assert user.updated_at == dt(11)
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, UserSettingsChanged)
    assert event.old_settings == default_settings()
    assert event.new_settings == user.settings


@pytest.mark.unit
def test_change_settings_noop_does_not_touch_updated_at() -> None:
    user = mk_user(now=dt(10))
    user.pull_events()
    updated_at_before = user.updated_at

    user.change_settings(descriptor=descriptor_lite(), at=dt(11))

    assert user.updated_at == updated_at_before
    assert user.pull_events() == []


@pytest.mark.unit
def test_change_settings_raises_when_tier_too_low() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(ModelSelectionError) as exc_info:
        user.change_settings(descriptor=descriptor_pro(), at=dt(11))
    assert exc_info.value.code == ModelSelectionCode.TIER_TOO_LOW


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_resolves_from_registry() -> None:
    user = mk_user(now=dt(10))
    user.change_subscription(
        actor=UserRole.OWNER,
        new_subscription=UserSubscription.premium(dt(10)),
        at=dt(10),
    )
    user.pull_events()
    repo = FakeModelRepo()

    await ModelSelectionService.select_model(
        user=user,
        model=Model.parse("gigachat-2-pro"),
        repo=repo,
        at=dt(11),
    )

    assert user.settings.model == Model.parse("gigachat-2-pro")
    assert user.updated_at == dt(11)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_raises_when_model_missing() -> None:
    user = mk_user(now=dt(10))
    repo = FakeModelRepo(entries={})

    with pytest.raises(ModelNotFoundError) as exc_info:
        await ModelSelectionService.select_model(
            user=user,
            model=Model.parse("unknown-model"),
            repo=repo,
            at=dt(11),
        )
    assert "unknown-model" in exc_info.value.model


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_selection_service_denies_premium_model_for_free_user() -> None:
    user = mk_user(now=dt(10))
    repo = FakeModelRepo()

    with pytest.raises(ModelSelectionError):
        await ModelSelectionService.select_model(
            user=user,
            model=Model.parse("gigachat-2-pro"),
            repo=repo,
            at=dt(11),
        )


@pytest.mark.unit
def test_user_restore_requires_settings() -> None:
    user = mk_user(now=dt(10))
    restored = User.restore(
        id=user.id,
        profile=user.profile,
        role=user.role,
        state=user.state,
        subscription=user.subscription,
        settings=user.settings,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_seen_at=user.last_seen_at,
    )
    assert restored.settings == user.settings
