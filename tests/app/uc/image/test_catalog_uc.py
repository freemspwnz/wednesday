"""Tests for ImageCatalogUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.use_cases.image import ImageCatalogUseCase
from domain.image import ImageScorePolicy
from domain.kernel.vo import AwareDatetime
from tests.dom.image.factories import mk_image

from ...factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_returns_none_when_catalog_empty() -> None:
    images = AsyncMock()
    views = AsyncMock()
    images.get_random_unseen_for_chat.return_value = None
    uow = FakeUoW(images=images, views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = UUID(int=99)

    result = await uc.pick_for_chat(chat_id=chat_id, at=dt(10))

    assert result is None
    images.get_random_unseen_for_chat.assert_awaited_once_with(
        chat_id,
        min_score=ImageScorePolicy.CATALOG_MIN_SCORE,
    )
    views.mark_shown.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_marks_shown_and_returns_card() -> None:
    image = mk_image(image_id=3, score=2, created_at=dt(9))
    images = AsyncMock()
    views = AsyncMock()
    images.get_random_unseen_for_chat.return_value = image
    uow = FakeUoW(images=images, views=views)
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = UUID(int=100)

    result = await uc.pick_for_chat(chat_id=chat_id, at=dt(10))

    assert isinstance(result, ImageCard)
    assert result.id == image.id
    assert result.score == 2
    views.mark_shown.assert_awaited_once_with(chat_id, image.id, at=dt(10))
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_runs_in_uow() -> None:
    image = mk_image(image_id=4, score=1, created_at=dt(9))
    uow = FakeUoW()
    uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = UUID(int=101)

    with patch(
        "app.use_cases.image.catalog.ImageCatalogService.pick_for_chat",
        new=AsyncMock(return_value=image),
    ) as pick:
        got = await uc.pick_for_chat(chat_id=chat_id, at=dt(11))

    assert got is not None
    assert got.id == image.id
    assert uow.enter_count == uow.exit_count == 1
    pick.assert_awaited_once_with(
        chat_id=chat_id,
        image_repo=uow.images,
        view_repo=uow.views,
        at=dt(11),
    )
