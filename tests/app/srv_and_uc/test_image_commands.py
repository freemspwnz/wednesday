"""Tests for ImageCommandService and ImageCommandsUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.services.image import ImageCommandService
from app.use_cases.image import ImageCommandsUseCase
from domain.image import ImageId, ImageNotFoundError
from domain.kernel.vo import AwareDatetime
from tests.dom.image.factories import FakeImageRepo, FakeImageVoteRepo, mk_image

from ..factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_returns_none_when_catalog_empty() -> None:
    images = AsyncMock()
    views = AsyncMock()
    images.get_random_unseen_for_chat.return_value = None
    srv = ImageCommandService(logger=mk_logger())
    chat_id = UUID(int=99)

    result = await srv.pick_for_chat(
        images=images,
        views=views,
        chat_id=chat_id,
        at=dt(10),
    )

    assert result is None
    images.get_random_unseen_for_chat.assert_awaited_once_with(chat_id, min_score=1)
    views.mark_shown.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_marks_shown_and_returns_card() -> None:
    image = mk_image(image_id=3, score=2, created_at=dt(9))
    images = AsyncMock()
    views = AsyncMock()
    images.get_random_unseen_for_chat.return_value = image
    srv = ImageCommandService(logger=mk_logger())
    chat_id = UUID(int=100)

    result = await srv.pick_for_chat(
        images=images,
        views=views,
        chat_id=chat_id,
        at=dt(10),
    )

    assert isinstance(result, ImageCard)
    assert result.id == image.id
    assert result.score == 2
    views.mark_shown.assert_awaited_once_with(chat_id, image.id, at=dt(10))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_runs_in_uow() -> None:
    image = mk_image(image_id=4, score=1, created_at=dt(9))
    images = AsyncMock()
    images.get_random_unseen_for_chat.return_value = image
    uow = FakeUoW(images=images)
    service = AsyncMock()
    service.pick_for_chat.return_value = ImageCard.from_domain(image)
    uc = ImageCommandsUseCase(uow=uow, service=service, logger=mk_logger())
    chat_id = UUID(int=101)

    got = await uc.pick_for_chat(chat_id=chat_id, at=dt(11))

    assert got is not None
    assert got.id == image.id
    assert uow.enter_count == uow.exit_count == 1
    service.pick_for_chat.assert_awaited_once_with(
        images=images,
        views=uow.views,
        chat_id=chat_id,
        at=dt(11),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_persists_score_in_uow() -> None:
    image = mk_image(image_id=11, score=1, created_at=dt(10))
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    uow = FakeUoW(images=image_repo, votes=vote_repo)
    uc = ImageCommandsUseCase(
        uow=uow,
        service=ImageCommandService(logger=mk_logger()),
        logger=mk_logger(),
    )
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
    image_repo = FakeImageRepo()
    vote_repo = FakeImageVoteRepo()
    uc = ImageCommandsUseCase(
        uow=FakeUoW(images=image_repo, votes=vote_repo),
        service=ImageCommandService(logger=mk_logger()),
        logger=mk_logger(),
    )

    with pytest.raises(ImageNotFoundError):
        await uc.vote(
            image_id=ImageId(UUID(int=404)),
            voter_id=UUID(int=502),
            value=-1,
            at=dt(11),
        )
