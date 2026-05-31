"""Тесты ImageVoteUseCase."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from dom.image.factories import FakeImageRepo, FakeImageVoteRepo, mk_image

from app.use_cases.image_vote import ImageVoteUseCase
from domain.image import ImageId
from domain.kernel.vo import AwareDatetime

from ..factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_persists_score_in_uow() -> None:
    image = mk_image(image_id=11, score=1, created_at=dt(10))
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    uow = FakeUoW(images=image_repo, votes=vote_repo)
    uc = ImageVoteUseCase(uow=uow, logger=mk_logger())
    voter_id = UUID(int=501)

    got = await uc.vote(
        image_id=image.id,
        voter_id=voter_id,
        value=1,
        at=dt(11),
    )

    assert got.score == 4
    assert uow.enter_count == uow.exit_count == 1
    assert vote_repo.votes[image.id, voter_id].value == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_propagates_image_not_found() -> None:
    from domain.image import ImageNotFoundError

    image_repo = FakeImageRepo()
    vote_repo = FakeImageVoteRepo()
    uc = ImageVoteUseCase(
        uow=FakeUoW(images=image_repo, votes=vote_repo),
        logger=mk_logger(),
    )

    with pytest.raises(ImageNotFoundError):
        await uc.vote(
            image_id=ImageId(UUID(int=404)),
            voter_id=UUID(int=502),
            value=-1,
            at=dt(11),
        )
