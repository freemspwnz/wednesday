import pytest

from domain.user import (
    AccessDeniedError,
    ActiveState,
    BannedState,
    StaleWriteError,
    User,
    UserRole,
)
from domain.user.exceptions import InvalidStateTransitionError, ModelSelectionError, ValidationError
from domain.user.policies.management import (
    ChangeRole,
    ManagementAccessCode,
    ManagementAllowed,
    ManagementDenied,
)
from domain.user.policies.model_selection import ModelSelectionCode

from .factories import descriptor_lite, descriptor_pro, dt, mk_user, plan_free


@pytest.mark.unit
def test_user_register_restore_and_ensure() -> None:
    user = mk_user(now=dt(10))
    assert isinstance(user.state, ActiveState)
    assert user.created_at == user.updated_at == user.last_seen_at == dt(10)

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
    assert User.ensure(restored) is restored


@pytest.mark.unit
def test_user_noop_commands_do_not_touch_updated_at() -> None:
    user = mk_user(now=dt(10))
    at_before = user.updated_at

    user.change_role(actor=UserRole.OWNER, new_role=user.role, at=dt(11))
    user.change_profile(actor=UserRole.SYSTEM, new_profile=user.profile, at=dt(11))
    user.change_subscription(actor=UserRole.ADMIN, new_subscription=user.subscription, at=dt(11))
    user.mark_seen_at(at=dt(10))

    assert user.updated_at == at_before
    assert user.pull_events() == []


@pytest.mark.unit
def test_ban_with_same_until_is_noop() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(12), at=dt(10))
    user.pull_events()
    updated_at_before = user.updated_at

    user.ban(actor=UserRole.OWNER, until=dt(12), at=dt(11))

    assert user.updated_at == updated_at_before
    assert user.pull_events() == []


@pytest.mark.unit
def test_user_guardrails_and_errors() -> None:
    user = mk_user(now=dt(10), role=UserRole.USER)
    with pytest.raises(AccessDeniedError):
        user.change_role(actor=UserRole.USER, new_role=UserRole.ADMIN, at=dt(11))
    with pytest.raises(InvalidStateTransitionError):
        user.unban(actor=UserRole.OWNER, at=dt(11))
    with pytest.raises(StaleWriteError):
        user.mark_seen_at(at=dt(9))
    with pytest.raises(ValidationError):
        user.change_profile(actor=UserRole.SYSTEM, new_profile="bad", at=dt(11))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        user._record_event("bad")  # type: ignore[arg-type]


@pytest.mark.unit
def test_validate_rejects_invalid_timestamps() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(ValidationError):
        User.restore(
            id=user.id,
            profile=user.profile,
            role=user.role,
            state=BannedState(until=dt(12)),
            subscription=user.subscription,
            settings=user.settings,
            created_at=dt(12),
            updated_at=dt(11),
            last_seen_at=dt(12),
        )


@pytest.mark.unit
def test_change_settings_noop_does_not_touch_updated_at() -> None:
    user = mk_user(now=dt(10))
    user.pull_events()
    updated_at_before = user.updated_at

    user.change_settings(fallback=plan_free(), descriptor=descriptor_lite(), at=dt(11))

    assert user.updated_at == updated_at_before
    assert user.pull_events() == []


@pytest.mark.unit
def test_change_settings_raises_when_tier_too_low() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(ModelSelectionError) as exc_info:
        user.change_settings(fallback=plan_free(), descriptor=descriptor_pro(), at=dt(11))
    assert exc_info.value.code == ModelSelectionCode.TIER_TOO_LOW


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


@pytest.mark.unit
def test_management_unknown_decision_is_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))
    action = ChangeRole(old_role=UserRole.USER, new_role=UserRole.ADMIN)

    monkeypatch.setattr("domain.user.user.ManagementAccessPolicy.evaluate", lambda _: object())
    with pytest.raises(ValidationError):
        user._ensure_management_allowed(actor=UserRole.OWNER, action=action)

    monkeypatch.setattr("domain.user.user.ManagementAccessPolicy.evaluate", lambda _: ManagementAllowed())
    user._ensure_management_allowed(actor=UserRole.OWNER, action=action)

    monkeypatch.setattr(
        "domain.user.user.ManagementAccessPolicy.evaluate",
        lambda _: ManagementDenied(code=ManagementAccessCode.ACCESS_DENIED),
    )
    with pytest.raises(AccessDeniedError):
        user._ensure_management_allowed(actor=UserRole.OWNER, action=action)
