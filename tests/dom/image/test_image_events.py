import pytest

from domain.image import (
    ActiveState,
    HiddenReason,
    ImageHidden,
    ImageRegistered,
    ImageScoreRecalculated,
    ImageShown,
)
from domain.image.events.base import ImageEvent
from domain.image.exceptions import ValidationError
from domain.user.vo import UserRole

from .factories import dt, mk_image


@pytest.mark.unit
def test_image_event_base_validation() -> None:
    with pytest.raises(ValidationError):
        ImageEvent(image_id="bad", occurred_at=dt(12))  # type: ignore[arg-type]


@pytest.mark.unit
def test_image_register_emits_registered_event() -> None:
    image = mk_image(created_at=dt(10))
    events = image.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ImageRegistered)
    assert event.occurred_at == dt(10)
    assert event.meta == image.meta
    assert event.prompts == image.prompts


@pytest.mark.unit
def test_image_recalculate_score_emits_event_on_change() -> None:
    image = mk_image()
    image.pull_events()

    image.recalculate_score([1], at=dt(11))
    events = image.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ImageScoreRecalculated)
    assert event.old_score == 3
    assert event.new_score == 4


@pytest.mark.unit
def test_image_recalculate_score_does_not_change_state_when_score_drops() -> None:
    image = mk_image()
    image.pull_events()

    image.recalculate_score([-1, -1, -1], at=dt(11))

    assert image.score == 0
    assert isinstance(image.state, ActiveState)
    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageScoreRecalculated)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "event_type"),
    [
        ("hide", ImageHidden),
        ("show", ImageShown),
    ],
)
def test_image_management_commands_emit_events(method: str, event_type: type) -> None:
    image = mk_image()
    image.pull_events()

    if method == "hide":
        image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    else:
        image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
        image.pull_events()
        image.show(actor=UserRole.OWNER, at=dt(12))

    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], event_type)
    assert events[0].actor == UserRole.OWNER


@pytest.mark.unit
def test_management_event_requires_actor() -> None:
    image = mk_image()
    with pytest.raises(ValidationError):
        ImageHidden(image_id=image.id, occurred_at=dt(11), actor="bad")  # type: ignore[arg-type]
