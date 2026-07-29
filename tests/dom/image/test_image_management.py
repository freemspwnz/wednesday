"""Tests for ImageManagementService."""

import pytest

from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    ImageManagementService,
    ImageNotFoundError,
    ImageRatingPolicy,
)
from domain.user import UserRole

from .factories import FakeImageRepo, dt, mk_image, mk_rating


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_hide_persists_admin_hidden_without_changing_rating() -> None:
    image = mk_image(rating=mk_rating(likes=5))
    image.pull_events()
    repo = FakeImageRepo.with_images(image)

    result = await ImageManagementService.hide(
        id=image.id,
        actor=UserRole.OWNER,
        repo=repo,
        at=dt(11),
    )

    assert isinstance(result.state, HiddenState)
    assert result.state.reason == HiddenReason.ADMIN
    assert result.rating == mk_rating(likes=5)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_show_after_admin_hide_resets_rating_to_default() -> None:
    image = mk_image(rating=mk_rating(likes=5))
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    image.pull_events()
    repo = FakeImageRepo.with_images(image)

    result = await ImageManagementService.show(
        id=image.id,
        actor=UserRole.OWNER,
        repo=repo,
        at=dt(12),
    )

    assert isinstance(result.state, ActiveState)
    assert result.rating == ImageRatingPolicy.default()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_show_from_rating_hidden_preserves_rating_for_system() -> None:
    image = mk_image(
        rating=mk_rating(likes=0, dislikes=1),
        state=HiddenState(reason=HiddenReason.RATING),
    )
    image.add_vote(new=1, old=None, at=dt(11))
    image.pull_events()
    repo = FakeImageRepo.with_images(image)

    result = await ImageManagementService.show(
        id=image.id,
        actor=UserRole.SYSTEM,
        repo=repo,
        at=dt(12),
    )

    assert isinstance(result.state, ActiveState)
    assert result.rating == mk_rating(likes=1, dislikes=1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_show_not_found() -> None:
    with pytest.raises(ImageNotFoundError):
        await ImageManagementService.show(
            id=mk_image(image_id=404).id,
            actor=UserRole.OWNER,
            repo=FakeImageRepo(),
            at=dt(11),
        )
