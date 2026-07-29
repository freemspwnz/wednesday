"""Tests for ImageCatalogService."""

from uuid import UUID

import pytest

from domain.chat import ChatId
from domain.image import ImageCatalogService, ImageRatingPolicy, ValidationError

from .factories import FakeViewRepo, dt, mk_image, mk_rating


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_returns_none_when_empty() -> None:
    views = FakeViewRepo()
    chat_id = ChatId(UUID(int=99))

    result = await ImageCatalogService.pick_for_chat(
        chat_id=chat_id,
        repo=views,
        at=dt(10),
    )

    assert result is None
    assert views.shown == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_marks_shown_and_returns_id() -> None:
    image = mk_image(image_id=5, rating=mk_rating(likes=2))
    views = FakeViewRepo(candidates=[image])
    chat_id = ChatId(UUID(int=100))

    result = await ImageCatalogService.pick_for_chat(
        chat_id=chat_id,
        repo=views,
        at=dt(10),
    )

    assert result == image.id
    assert (chat_id.value, image.id) in views.shown


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_uses_showable_min_rating() -> None:
    image = mk_image(image_id=6, rating=mk_rating(likes=1))
    views = FakeViewRepo(candidates=[image])
    chat_id = ChatId(UUID(int=101))

    result = await ImageCatalogService.pick_for_chat(
        chat_id=chat_id,
        repo=views,
        at=dt(10),
    )

    assert result == image.id
    assert ImageRatingPolicy.is_selectable(image.rating)
    assert ImageRatingPolicy.SHOWABLE_RATING == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_rejects_invalid_chat_id() -> None:
    with pytest.raises(ValidationError):
        await ImageCatalogService.pick_for_chat(
            chat_id="bad",  # type: ignore[arg-type]
            repo=FakeViewRepo(),
            at=dt(10),
        )
