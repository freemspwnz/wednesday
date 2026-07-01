from __future__ import annotations

from uuid import UUID

import pytest

from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    ImageManagementService,
    ImageNotFoundError,
    ImageShown,
)
from domain.image.policies import ImageScorePolicy
from domain.image.vote import Vote
from domain.user.vo import UserRole

from .factories import FakeImageRepo, FakeImageVoteRepo, dt, mk_image


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_hide_persists_admin_hidden_without_changing_score() -> None:
    image = mk_image(score=5)
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)

    result = await ImageManagementService.hide(
        image_id=image.id,
        actor=UserRole.OWNER,
        image_repo=image_repo,
        at=dt(11),
    )

    assert result.score == 5
    assert isinstance(result.state, HiddenState)
    assert result.state.reason == HiddenReason.ADMIN
    assert image_repo.save_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_show_after_admin_hide_resets_votes_and_base_score() -> None:
    image = mk_image()
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()

    await vote_repo.upsert(Vote(image_id=image.id, voter_id=UUID(int=2), value=1))
    await vote_repo.upsert(Vote(image_id=image.id, voter_id=UUID(int=3), value=1))
    image.recalculate_score([1, 1], at=dt(12))
    image_repo.images[image.id] = image

    result = await ImageManagementService.show(
        image_id=image.id,
        actor=UserRole.OWNER,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )

    assert isinstance(result.state, ActiveState)
    assert result.score == ImageScorePolicy.BASE
    assert await vote_repo.list_for_image(image.id) == []
    assert image_repo.save_calls == 1

    events = result.pull_events()
    shown_events = [event for event in events if isinstance(event, ImageShown)]
    assert len(shown_events) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_show_from_score_hidden_does_not_reset_votes() -> None:
    image = mk_image(score=0, state=HiddenState(reason=HiddenReason.SCORE))
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()

    from domain.image.vote import Vote

    await vote_repo.upsert(Vote(image_id=image.id, voter_id=UUID(int=2), value=-1))
    await vote_repo.upsert(Vote(image_id=image.id, voter_id=UUID(int=3), value=-1))
    await vote_repo.upsert(Vote(image_id=image.id, voter_id=UUID(int=4), value=-1))

    result = await ImageManagementService.show(
        image_id=image.id,
        actor=UserRole.OWNER,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(11),
    )

    assert isinstance(result.state, ActiveState)
    assert result.score == ImageScorePolicy.BASE
    assert len(await vote_repo.list_for_image(image.id)) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_management_show_raises_when_image_missing() -> None:
    image = mk_image()
    with pytest.raises(ImageNotFoundError):
        await ImageManagementService.show(
            image_id=image.id,
            actor=UserRole.OWNER,
            image_repo=FakeImageRepo(),
            vote_repo=FakeImageVoteRepo(),
            at=dt(11),
        )
