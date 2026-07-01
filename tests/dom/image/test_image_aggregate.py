import pytest

from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    Image,
    ImageScoreRecalculated,
    ImageState,
    TelegramFileId,
)
from domain.image.exceptions import AccessDeniedError, ValidationError
from domain.user.vo import UserRole

from .factories import dt, mk_image


@pytest.mark.unit
def test_image_register_restore_and_ensure() -> None:
    image = mk_image(created_at=dt(10))
    assert image.score == 3
    assert image.is_selectable
    assert isinstance(image.state, ActiveState)
    assert image.file_id == TelegramFileId.parse("AgACAgIAAxkBAAI")
    assert image.prompts.enriched is not None

    restored = Image.restore(
        id=image.id,
        meta=image.meta,
        created_at=image.created_at,
        score=image.score,
        state=image.state,
        file_id=image.file_id,
        prompts=image.prompts,
    )
    assert Image.ensure(restored) is restored


@pytest.mark.unit
def test_recalculate_score_updates_score_without_changing_state() -> None:
    image = mk_image(score=0, state=HiddenState(reason=HiddenReason.SCORE))
    image.pull_events()

    image.recalculate_score([1, 1], at=dt(13))

    assert image.score == 5
    assert isinstance(image.state, HiddenState)
    assert image.state.reason == HiddenReason.SCORE
    assert not image.is_selectable


@pytest.mark.unit
def test_system_show_from_score_hidden_preserves_score() -> None:
    image = mk_image(score=0, state=HiddenState(reason=HiddenReason.SCORE))
    image.pull_events()
    image.recalculate_score([1, 1], at=dt(12))

    image.show(actor=UserRole.SYSTEM, at=dt(13))

    assert image.score == 5
    assert isinstance(image.state, ActiveState)
    assert image.is_selectable


@pytest.mark.unit
@pytest.mark.parametrize(
    ("actor", "method"),
    [
        (UserRole.OWNER, "hide"),
        (UserRole.SYSTEM, "hide"),
        (UserRole.OWNER, "show"),
    ],
)
def test_image_hide_and_show(actor: UserRole, method: str) -> None:
    image = mk_image()
    image.pull_events()

    if method == "show":
        image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(10))
        image.pull_events()

    if method == "hide":
        reason = HiddenReason.SCORE if actor == UserRole.SYSTEM else HiddenReason.ADMIN
        image.hide(actor=actor, reason=reason, at=dt(11))
    else:
        image.show(actor=actor, at=dt(11))

    if method == "hide":
        assert image.score == 3
        assert isinstance(image.state, HiddenState)
        expected_reason = HiddenReason.SCORE if actor == UserRole.SYSTEM else HiddenReason.ADMIN
        assert image.state.reason == expected_reason
        assert image.is_hidden
        assert not image.is_selectable
    else:
        assert image.score == 3
        assert isinstance(image.state, ActiveState)
        assert image.is_selectable


@pytest.mark.unit
def test_image_admin_hide_and_show_sequence() -> None:
    image = mk_image()
    image.pull_events()

    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    assert image.score == 3
    image.show(actor=UserRole.OWNER, at=dt(12))
    assert isinstance(image.state, ActiveState)
    assert image.score == 3


@pytest.mark.unit
@pytest.mark.parametrize(
    ("actor", "method"),
    [
        (UserRole.ADMIN, "show"),
        (UserRole.USER, "hide"),
        (UserRole.USER, "show"),
    ],
)
def test_image_management_access_denied(actor: UserRole, method: str) -> None:
    image = mk_image()
    with pytest.raises(AccessDeniedError):
        if method == "hide":
            image.hide(actor=actor, reason=HiddenReason.ADMIN, at=dt(11))
        else:
            image.show(actor=actor, at=dt(11))


@pytest.mark.unit
def test_image_admin_can_hide_but_not_show() -> None:
    image = mk_image()
    image.hide(actor=UserRole.ADMIN, reason=HiddenReason.ADMIN, at=dt(11))
    assert image.is_hidden

    with pytest.raises(AccessDeniedError):
        image.show(actor=UserRole.ADMIN, at=dt(12))


@pytest.mark.unit
def test_image_hide_is_idempotent() -> None:
    image = mk_image()
    image.pull_events()
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    assert len(image.pull_events()) == 1
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(12))
    assert image.pull_events() == []


@pytest.mark.unit
def test_image_show_is_idempotent_after_hide() -> None:
    image = mk_image()
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    image.pull_events()
    image.show(actor=UserRole.OWNER, at=dt(12))
    assert len(image.pull_events()) == 1
    image.show(actor=UserRole.OWNER, at=dt(13))
    assert image.pull_events() == []


@pytest.mark.unit
def test_image_register_custom_score_via_restore() -> None:
    image = mk_image(score=5)
    assert image.score == 5


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "state", "message"),
    [
        (3, HiddenState(reason=HiddenReason.SCORE), "score-hidden image must not have a selectable score"),
        (0, ActiveState(), "active image must have a selectable score"),
    ],
)
def test_image_validate_rejects_incoherent_state(score: int, state: ImageState, message: str) -> None:
    base = mk_image()
    with pytest.raises(ValidationError, match=message):
        Image.restore(
            id=base.id,
            meta=base.meta,
            created_at=dt(10),
            score=score,
            state=state,
            file_id=base.file_id,
            prompts=base.prompts,
        )


@pytest.mark.unit
def test_image_validate_allows_admin_hidden_with_positive_score() -> None:
    image = Image.restore(
        id=mk_image().id,
        meta=mk_image().meta,
        created_at=dt(10),
        score=6,
        state=HiddenState(reason=HiddenReason.ADMIN),
        file_id=mk_image().file_id,
        prompts=mk_image().prompts,
    )
    assert image.score == 6
    assert image.state.reason == HiddenReason.ADMIN


@pytest.mark.unit
def test_recalculate_score_noop_emits_no_event() -> None:
    image = mk_image()
    image.pull_events()

    image.recalculate_score([], at=dt(11))
    assert image.pull_events() == []


@pytest.mark.unit
def test_recalculate_score_keeps_admin_hidden_but_updates_score() -> None:
    image = mk_image()
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    image.pull_events()

    image.recalculate_score([1, 1, 1], at=dt(12))

    assert image.score == 6
    assert isinstance(image.state, HiddenState)
    assert image.state.reason == HiddenReason.ADMIN
    assert not image.is_selectable
    assert image.is_hidden

    events = image.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ImageScoreRecalculated)
    assert event.old_score == 3
    assert event.new_score == 6


@pytest.mark.unit
def test_hide_over_score_hidden_switches_reason_to_admin() -> None:
    image = mk_image(score=0, state=HiddenState(reason=HiddenReason.SCORE))
    image.pull_events()

    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))

    assert isinstance(image.state, HiddenState)
    assert image.state.reason == HiddenReason.ADMIN
    assert image.score == 0
