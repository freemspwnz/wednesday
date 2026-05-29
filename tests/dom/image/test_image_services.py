from __future__ import annotations

from uuid import UUID

import pytest

from domain.image import ImageNotFoundError, ImageScoreRecalculated, ImageVoteService
from domain.image.exceptions import ValidationError
from domain.image.vo.states import HiddenReason, HiddenStatus

from .factories import FakeImageRepo, FakeImageVoteRepo, dt, mk_image


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_inserts_vote_recalculates_and_saves() -> None:
    image = mk_image()
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    voter_id = UUID(int=2)

    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )

    assert result.score == 4
    assert image_repo.save_calls == 1
    assert len(vote_repo.votes) == 1
    events = result.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ImageScoreRecalculated)
    assert events[0].old_score == 3
    assert events[0].new_score == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_updates_existing_vote() -> None:
    image = mk_image()
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    voter_id = UUID(int=2)

    await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )
    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=-1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(14),
    )

    assert result.score == 2
    assert image_repo.save_calls == 2
    assert len(vote_repo.votes) == 1
    assert vote_repo.votes[image.id, voter_id].value == -1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_same_vote_is_noop_without_save() -> None:
    image = mk_image()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    voter_id = UUID(int=2)

    first = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(13),
    )
    first.pull_events()
    saved_before = image_repo.save_calls

    result = await ImageVoteService.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        image_repo=image_repo,
        vote_repo=vote_repo,
        at=dt(14),
    )

    assert result.score == 4
    assert image_repo.save_calls == saved_before
    assert result.pull_events() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_hides_image_when_score_drops_to_zero() -> None:
    image = mk_image()
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()

    result = image
    for voter in (2, 3, 4):
        result = await ImageVoteService.vote(
            image_id=image.id,
            voter_id=UUID(int=voter),
            value=-1,
            image_repo=image_repo,
            vote_repo=vote_repo,
            at=dt(13),
        )

    assert result.score == 0
    assert result.is_hidden
    assert isinstance(result.status, HiddenStatus)
    assert result.status.reason == HiddenReason.VOTES


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_raises_when_image_missing() -> None:
    image = mk_image()
    with pytest.raises(ImageNotFoundError) as exc_info:
        await ImageVoteService.vote(
            image_id=image.id,
            voter_id=UUID(int=2),
            value=1,
            image_repo=FakeImageRepo(),
            vote_repo=FakeImageVoteRepo(),
            at=dt(13),
        )
    assert str(image.id) in exc_info.value.image_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vote_service_validates_voter_id() -> None:
    image = mk_image()
    image_repo = FakeImageRepo.with_images(image)
    with pytest.raises(ValidationError):
        await ImageVoteService.vote(
            image_id=image.id,
            voter_id="bad",  # type: ignore[arg-type]
            value=1,
            image_repo=image_repo,
            vote_repo=FakeImageVoteRepo(),
            at=dt(13),
        )
