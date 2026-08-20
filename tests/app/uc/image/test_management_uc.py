"""Tests for ImageManagementUseCase."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.use_cases.image import ImageManagementUseCase
from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    ImageId,
    ImageNotFoundError,
    Vote,
)
from domain.kernel.vo import AwareDatetime
from domain.user import UserId, UserRole
from tests.dom.image.factories import FakeImageRepo, FakeImageVoteRepo, mk_image, mk_rating

from ...factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_hide_persists_admin_hidden() -> None:
    image = mk_image(image_id=7, rating=mk_rating(likes=2), created_at=dt(10))
    image_repo = FakeImageRepo.with_images(image)
    uow = FakeUoW(images=image_repo)
    uc = ImageManagementUseCase(uow=uow, logger=mk_logger())

    got = await uc.hide(image_id=str(image.id), actor=int(UserRole.OWNER), at=dt(11).value)

    assert isinstance(got.state, HiddenState)
    assert got.state.reason == HiddenReason.ADMIN
    assert got.rating == mk_rating(likes=2)
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_show_after_admin_hide_resets_votes() -> None:
    image = mk_image(image_id=8, rating=mk_rating(likes=2), created_at=dt(10))
    image.hide(actor=UserRole.OWNER, reason=HiddenReason.ADMIN, at=dt(11))
    image.pull_events()
    image_repo = FakeImageRepo.with_images(image)
    vote_repo = FakeImageVoteRepo()
    await vote_repo.upsert(Vote(image_id=image.id, voter_id=UserId(UUID(int=1)), value=1))
    uow = FakeUoW(images=image_repo, votes=vote_repo)
    uc = ImageManagementUseCase(uow=uow, logger=mk_logger())

    got = await uc.show(image_id=str(image.id), actor=int(UserRole.OWNER), at=dt(12).value)

    assert isinstance(got.state, ActiveState)
    assert await vote_repo.list_for_image(image.id) == []
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_show_propagates_image_not_found() -> None:
    uc = ImageManagementUseCase(
        uow=FakeUoW(images=FakeImageRepo(), votes=FakeImageVoteRepo()),
        logger=mk_logger(),
    )
    with pytest.raises(ImageNotFoundError):
        await uc.show(
            image_id=str(ImageId(UUID(int=404))),
            actor=int(UserRole.OWNER),
            at=dt(11).value,
        )
