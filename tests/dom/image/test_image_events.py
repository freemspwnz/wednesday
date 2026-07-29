"""Tests for image domain events."""

import pytest

from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    ImageHidden,
    ImageRatingChanged,
    ImageShown,
)
from domain.user import UserRole

from .factories import dt, mk_image, mk_rating


@pytest.mark.unit
def test_image_add_vote_emits_rating_changed_on_change() -> None:
    image = mk_image()
    image.pull_events()

    image.add_vote(new=1, old=None, at=dt(11))

    events = image.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ImageRatingChanged)
    assert event.old == mk_rating(likes=3)
    assert event.new == mk_rating(likes=4)


@pytest.mark.unit
def test_image_add_vote_does_not_change_state_when_rating_drops() -> None:
    image = mk_image()
    image.pull_events()

    image.add_vote(new=-1, old=None, at=dt(11))
    image.add_vote(new=-1, old=None, at=dt(11))
    image.add_vote(new=-1, old=None, at=dt(11))

    assert image.rating == mk_rating(likes=3, dislikes=3)
    assert isinstance(image.state, ActiveState)
    events = image.pull_events()
    assert len(events) == 3
    assert isinstance(events[0], ImageRatingChanged)


@pytest.mark.unit
def test_image_hide_and_show_emit_events() -> None:
    image = mk_image()
    image.pull_events()

    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    hide_events = image.pull_events()
    assert len(hide_events) == 1
    assert isinstance(hide_events[0], ImageHidden)

    image.show(actor=UserRole.OWNER, at=dt(12))
    show_events = image.pull_events()
    assert len(show_events) == 1
    assert isinstance(show_events[0], ImageShown)


@pytest.mark.unit
def test_image_hide_noop_when_already_same_reason() -> None:
    image = mk_image(state=HiddenState(reason=HiddenReason.ADMIN))
    image.pull_events()

    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))

    assert image.pull_events() == []
