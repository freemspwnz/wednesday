"""Tests for ImageVoteUseCase."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.use_cases.image import ImageCatalogUseCase, ImageVoteUseCase
from domain.chat import ChatId
from domain.image import ImageId, ImageNotFoundError, Vote
from domain.kernel.vo import AwareDatetime
from domain.user import UserId
from tests.dom.image.factories import FakeImageRepo, FakeImageVoteRepo, FakeViewRepo, mk_image, mk_rating

from ...factories import FakeUoW, mk_logger

_PRIVATE_CHAT_ID = ChatId(UUID(int=1))
_OTHER_CHAT_ID = ChatId(UUID(int=2))
_VOTER_ID = UserId(UUID(int=501))


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_persists_rating_in_uow() -> None:
    image = mk_image(image_id=11, rating=mk_rating(likes=1), created_at=dt(10))
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    views = FakeViewRepo()
    uow = FakeUoW(images=image_repo, votes=vote_repo, views=views)
    uc = ImageVoteUseCase(uow=uow, logger=mk_logger())

    got = await uc.vote(
        image_id=image.id,
        voter_id=_VOTER_ID,
        chat_id=_PRIVATE_CHAT_ID,
        value=1,
        at=dt(11),
    )

    assert isinstance(got, ImageCard)
    assert got.rating == mk_rating(likes=2)
    assert uow.enter_count == uow.exit_count == 1
    assert vote_repo.votes[image.id, _VOTER_ID].value == 1
    assert (_PRIVATE_CHAT_ID.value, image.id) in views.shown


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_noop_still_marks_shown() -> None:
    image = mk_image(image_id=12, rating=mk_rating(likes=2), created_at=dt(10))
    vote_repo = FakeImageVoteRepo()
    views = FakeViewRepo()
    await vote_repo.upsert(Vote(image_id=image.id, voter_id=_VOTER_ID, value=1))
    uow = FakeUoW(images=FakeImageRepo.with_images(image), votes=vote_repo, views=views)
    uc = ImageVoteUseCase(uow=uow, logger=mk_logger())

    got = await uc.vote(
        image_id=image.id,
        voter_id=_VOTER_ID,
        chat_id=_PRIVATE_CHAT_ID,
        value=1,
        at=dt(11),
    )

    assert got is None
    assert (_PRIVATE_CHAT_ID.value, image.id) in views.shown


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_hides_image_from_private_chat_random() -> None:
    image = mk_image(image_id=13, rating=mk_rating(likes=2), created_at=dt(10))
    image_repo = FakeImageRepo.with_images(image)
    views = FakeViewRepo(candidates=[image])
    uow = FakeUoW(images=image_repo, votes=FakeImageVoteRepo(), views=views)
    vote_uc = ImageVoteUseCase(uow=uow, logger=mk_logger())
    catalog_uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())

    await vote_uc.vote(
        image_id=image.id,
        voter_id=_VOTER_ID,
        chat_id=_PRIVATE_CHAT_ID,
        value=1,
        at=dt(11),
    )

    assert await catalog_uc.pick_for_chat(chat_id=_PRIVATE_CHAT_ID) is None
    picked = await catalog_uc.pick_for_chat(chat_id=_OTHER_CHAT_ID)
    assert picked is not None
    assert picked.id == image.id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_vote_propagates_image_not_found() -> None:
    views = FakeViewRepo()
    uc = ImageVoteUseCase(
        uow=FakeUoW(images=FakeImageRepo(), votes=FakeImageVoteRepo(), views=views),
        logger=mk_logger(),
    )
    missing = ImageId(UUID(int=404))
    with pytest.raises(ImageNotFoundError):
        await uc.vote(
            image_id=missing,
            voter_id=UserId(UUID(int=502)),
            chat_id=_PRIVATE_CHAT_ID,
            value=-1,
            at=dt(11),
        )
    assert views.shown == set()
