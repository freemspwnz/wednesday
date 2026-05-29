import pytest

from domain.image import (
    ImageAdminHidden,
    ImageAdminRestored,
    ImageFileAttached,
    ImageRegistered,
    ImageScoreRecalculated,
    TelegramFileId,
)
from domain.image.events.base import ImageEvent
from domain.image.exceptions import ValidationError

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


@pytest.mark.unit
def test_image_attach_file_id_emits_event() -> None:
    image = mk_image()
    image.pull_events()

    file_id = TelegramFileId.parse("AgACAgIAAxkBAAI")
    image.attach_file_id(file_id, at=dt(11))

    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageFileAttached)
    assert events[0].file_id == file_id


@pytest.mark.unit
def test_image_recalculate_score_emits_event_on_change() -> None:
    image = mk_image()
    image.pull_events()

    image.recalculate_score([1], at=dt(11))
    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageScoreRecalculated)
    assert events[0].old_score == 3
    assert events[0].new_score == 4


@pytest.mark.unit
def test_image_admin_commands_emit_events_and_noop() -> None:
    image = mk_image()
    image.pull_events()

    image.admin_hide(at=dt(11))
    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageAdminHidden)

    image.admin_hide(at=dt(12))
    assert image.pull_events() == []

    image.admin_restore(at=dt(13))
    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageAdminRestored)

    image.admin_restore(at=dt(14))
    assert image.pull_events() == []
