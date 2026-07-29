"""Tests for Image aggregate rating / visibility behavior."""

import pytest

from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    Image,
    ImageHidden,
    ImageId,
    ImageRating,
    ImageRatingChanged,
    ImageRegistered,
    ImageShown,
    ImageState,
    ValidationError,
)
from domain.user import UserRole

from .factories import dt, mk_file_id, mk_image, mk_meta, mk_prompts, mk_rating


@pytest.mark.unit
def test_image_register_defaults() -> None:
    image = mk_image()
    assert image.rating == ImageRating(likes=3, dislikes=0)
    assert isinstance(image.state, ActiveState)
    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageRegistered)


@pytest.mark.unit
def test_image_restore_roundtrip() -> None:
    image = mk_image(rating=mk_rating(likes=5))
    restored = Image.restore(
        id=image.id,
        meta=image.meta,
        rating=image.rating,
        state=image.state,
        file_id=image.file_id,
        prompts=image.prompts,
        created_at=image.created_at,
    )
    assert restored.rating == image.rating
    assert restored.id == image.id


@pytest.mark.unit
def test_add_vote_updates_rating_without_changing_state() -> None:
    image = mk_image(rating=mk_rating(likes=0, dislikes=1), state=HiddenState(reason=HiddenReason.RATING))
    image.pull_events()

    image.add_vote(new=1, old=None, at=dt(13))

    assert image.rating == mk_rating(likes=1, dislikes=1)
    assert isinstance(image.state, HiddenState)
    assert image.state.reason == HiddenReason.RATING
    events = image.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageRatingChanged)


@pytest.mark.unit
def test_system_show_from_rating_hidden_preserves_rating() -> None:
    image = mk_image(rating=mk_rating(likes=0, dislikes=1), state=HiddenState(reason=HiddenReason.RATING))
    image.add_vote(new=1, old=None, at=dt(12))
    image.add_vote(new=1, old=None, at=dt(12))
    image.pull_events()

    image.show(actor=UserRole.SYSTEM, at=dt(13))

    assert image.rating == mk_rating(likes=2, dislikes=1)
    assert isinstance(image.state, ActiveState)
    assert isinstance(image.pull_events()[0], ImageShown)


@pytest.mark.unit
@pytest.mark.parametrize("actor", [UserRole.SYSTEM, UserRole.OWNER, UserRole.ADMIN])
def test_hide_and_owner_show(actor: UserRole) -> None:
    image = mk_image()
    image.pull_events()

    if actor in {UserRole.SYSTEM, UserRole.OWNER, UserRole.ADMIN}:
        reason = HiddenReason.RATING if actor == UserRole.SYSTEM else HiddenReason.ADMIN
        image.hide(actor=actor, reason=reason, at=dt(11))
        assert isinstance(image.state, HiddenState)
        assert image.rating == mk_rating(likes=3)
        expected_reason = HiddenReason.RATING if actor == UserRole.SYSTEM else HiddenReason.ADMIN
        assert image.state.reason == expected_reason
        assert isinstance(image.pull_events()[0], ImageHidden)

    if actor == UserRole.OWNER:
        image.show(actor=actor, at=dt(12))
        assert isinstance(image.state, ActiveState)
        assert image.rating == mk_rating(likes=3)
        assert isinstance(image.pull_events()[0], ImageShown)


@pytest.mark.unit
def test_owner_show_resets_rating_to_default() -> None:
    image = mk_image(rating=mk_rating(likes=1, dislikes=2), state=HiddenState(reason=HiddenReason.ADMIN))
    image.pull_events()

    image.show(actor=UserRole.OWNER, at=dt(12))

    assert image.rating == mk_rating(likes=3)
    assert isinstance(image.state, ActiveState)


@pytest.mark.unit
def test_image_register_custom_rating_via_restore() -> None:
    image = mk_image(rating=mk_rating(likes=5))
    assert image.rating == mk_rating(likes=5)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rating", "state", "message"),
    [
        (
            mk_rating(likes=3),
            HiddenState(reason=HiddenReason.RATING),
            "rating-hidden image must not have a selectable rating",
        ),
        (mk_rating(likes=0, dislikes=1), ActiveState(), "active image must have a selectable rating"),
    ],
)
def test_image_validate_rejects_incoherent_state(
    rating: ImageRating,
    state: ImageState,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Image.restore(
            id=ImageId.new(),
            meta=mk_meta(),
            rating=rating,
            state=state,
            file_id=mk_file_id(),
            prompts=mk_prompts(),
            created_at=dt(10),
        )


@pytest.mark.unit
def test_image_validate_allows_admin_hidden_with_positive_rating() -> None:
    image = Image.restore(
        id=ImageId.new(),
        meta=mk_meta(),
        rating=mk_rating(likes=6),
        state=HiddenState(reason=HiddenReason.ADMIN),
        file_id=mk_file_id(),
        prompts=mk_prompts(),
        created_at=dt(10),
    )
    assert image.rating == mk_rating(likes=6)


@pytest.mark.unit
def test_add_vote_noop_emits_no_event() -> None:
    image = mk_image()
    image.pull_events()

    image.add_vote(new=1, old=1, at=dt(11))

    assert image.pull_events() == []


@pytest.mark.unit
def test_add_vote_keeps_admin_hidden_but_updates_rating() -> None:
    image = mk_image(state=HiddenState(reason=HiddenReason.ADMIN))
    image.pull_events()

    image.add_vote(new=1, old=None, at=dt(12))
    image.add_vote(new=1, old=None, at=dt(12))
    image.add_vote(new=1, old=None, at=dt(12))

    assert image.rating == mk_rating(likes=6)
    assert isinstance(image.state, HiddenState)
    assert image.state.reason == HiddenReason.ADMIN
    events = image.pull_events()
    assert len(events) == 3
    event = events[-1]
    assert isinstance(event, ImageRatingChanged)
    assert event.old == mk_rating(likes=5)
    assert event.new == mk_rating(likes=6)


@pytest.mark.unit
def test_hide_over_rating_hidden_switches_reason_to_admin() -> None:
    image = mk_image(rating=mk_rating(likes=0, dislikes=1), state=HiddenState(reason=HiddenReason.RATING))
    image.pull_events()

    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))

    assert isinstance(image.state, HiddenState)
    assert image.state.reason == HiddenReason.ADMIN
    assert image.rating == mk_rating(likes=0, dislikes=1)
