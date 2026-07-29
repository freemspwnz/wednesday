"""Tests for ImageVoteUseCase."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.use_cases.image import ImageVoteUseCase
from domain.image import ImageId, ImageNotFoundError
from domain.kernel.vo import AwareDatetime
from domain.user import UserId
from tests.dom.image.factories import FakeImageRepo, FakeImageVoteRepo, mk_image, mk_rating

from ...factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_persists_rating_in_uow() -> None:
    image = mk_image(image_id=11, rating=mk_rating(likes=1), created_at=dt(10))
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    uow = FakeUoW(images=image_repo, votes=vote_repo)
    uc = ImageVoteUseCase(uow=uow, logger=mk_logger())
    voter_id = UserId(UUID(int=501))

    got = await uc.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        at=dt(11),
    )

    assert isinstance(got, ImageCard)
    assert got.rating == mk_rating(likes=2)
    assert uow.enter_count == uow.exit_count == 1
    assert vote_repo.votes[image.id, voter_id].value == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_noop_returns_none_when_same_value() -> None:
    image = mk_image(image_id=12, rating=mk_rating(likes=2), created_at=dt(10))
    vote_repo = FakeImageVoteRepo()
    from domain.image import Vote

    await vote_repo.upsert(Vote(image_id=image.id, voter_id=UserId(UUID(int=501)), value=1))
    uow = FakeUoW(images=FakeImageRepo.with_images(image), votes=vote_repo)
    uc = ImageVoteUseCase(uow=uow, logger=mk_logger())

    got = await uc.vote(
        image_id=image.id,
        voter_id=UserId(UUID(int=501)),
        value=1,
        at=dt(11),
    )

    assert got is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_propagates_image_not_found() -> None:
    image_repo = FakeImageRepo()
    vote_repo = FakeImageVoteRepo()
    uc = ImageVoteUseCase(
        uow=FakeUoW(images=image_repo, votes=vote_repo),
        logger=mk_logger(),
    )
    with pytest.raises(ImageNotFoundError):
        await uc.vote(
            image_id=ImageId(UUID(int=404)),
            voter_id=UserId(UUID(int=502)),
            value=-1,
            at=dt(11),
        )
