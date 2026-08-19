"""Tests for ImageCatalogUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.use_cases.image import ImageCatalogUseCase
from domain.chat import ChatId
from domain.image import ImageId, ImageNotFoundError, ImageRatingPolicy
from domain.kernel.vo import AwareDatetime
from tests.dom.image.factories import FakeImageRepo, FakeViewRepo, mk_image, mk_rating

from ...factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reset_views_delegates_to_repo() -> None:
    image = mk_image(image_id=3, rating=mk_rating(likes=2), created_at=dt(9))
    repo = FakeViewRepo(candidates=[image])
    chat_id = ChatId(UUID(int=100))
    other_chat_id = ChatId(UUID(int=101))
    repo.shown = {
        (chat_id.value, image.id),
        (other_chat_id.value, image.id),
    }
    uow = FakeUoW(views=repo)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())

    result = await uc.reset_views(chat_id=chat_id)

    assert result == 1
    assert (chat_id.value, image.id) not in repo.shown
    assert (other_chat_id.value, image.id) in repo.shown
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reset_views_allows_pick_again() -> None:
    image = mk_image(image_id=5, rating=mk_rating(likes=2), created_at=dt(9))
    views = FakeViewRepo(candidates=[image])
    images = FakeImageRepo.with_images(image)
    uow = FakeUoW(images=images, views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = ChatId(UUID(int=200))

    await uc.mark_shown(chat_id=chat_id, image_id=image.id, at=dt(10))
    assert await uc.pick_for_chat(chat_id=chat_id) is None

    count = await uc.reset_views(chat_id=chat_id)
    assert count == 1
    card = await uc.pick_for_chat(chat_id=chat_id)
    assert card is not None
    assert card.id == image.id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_returns_none_when_catalog_empty() -> None:
    views = AsyncMock()
    views.get_unseen_for_chat.return_value = None
    uow = FakeUoW(views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = ChatId(UUID(int=99))

    result = await uc.pick_for_chat(chat_id=chat_id)

    assert result is None
    views.get_unseen_for_chat.assert_awaited_once_with(
        chat_id=chat_id,
        min_rating=ImageRatingPolicy.SHOWABLE_RATING,
    )
    views.mark_shown.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_returns_card_without_marking() -> None:
    image = mk_image(image_id=3, rating=mk_rating(likes=2), created_at=dt(9))
    views = FakeViewRepo(candidates=[image])
    images = FakeImageRepo.with_images(image)
    uow = FakeUoW(images=images, views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = ChatId(UUID(int=100))

    result = await uc.pick_for_chat(chat_id=chat_id)

    assert isinstance(result, ImageCard)
    assert result.id == image.id
    assert result.rating == mk_rating(likes=2)
    assert (chat_id.value, image.id) not in views.shown
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_mark_shown_records_view() -> None:
    image = mk_image(image_id=3, rating=mk_rating(likes=2), created_at=dt(9))
    views = FakeViewRepo(candidates=[image])
    uow = FakeUoW(views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = ChatId(UUID(int=100))

    await uc.mark_shown(chat_id=chat_id, image_id=image.id, at=dt(10))

    assert (chat_id.value, image.id) in views.shown
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_runs_in_uow() -> None:
    image = mk_image(image_id=4, rating=mk_rating(likes=1), created_at=dt(9))
    views = FakeViewRepo(candidates=[image])
    uow = FakeUoW(images=FakeImageRepo.with_images(image), views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = ChatId(UUID(int=101))

    got = await uc.pick_for_chat(chat_id=chat_id)

    assert got is not None
    assert got.id == image.id
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_raises_when_image_missing() -> None:
    views = AsyncMock()
    views.get_unseen_for_chat.return_value = ImageId(UUID(int=77))
    views.mark_shown = AsyncMock()
    uow = FakeUoW(images=FakeImageRepo(), views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())

    with pytest.raises(ImageNotFoundError):
        await uc.pick_for_chat(chat_id=ChatId(UUID(int=102)))

    views.mark_shown.assert_not_awaited()
