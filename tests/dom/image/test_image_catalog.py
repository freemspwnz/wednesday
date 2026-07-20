from __future__ import annotations

from uuid import UUID

import pytest

from domain.image import ImageCatalogService, ImageScorePolicy, ValidationError

from .factories import FakeImageRepo, FakeViewRepo, dt, mk_image


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_returns_none_when_empty() -> None:
    chat_id = UUID(int=10)
    views = FakeViewRepo()

    result = await ImageCatalogService.pick_for_chat(
        chat_id=chat_id,
        image_repo=FakeImageRepo(),
        view_repo=views,
        at=dt(12),
    )

    assert result is None
    assert views.shown == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_marks_shown_and_returns_image() -> None:
    image = mk_image(image_id=5, score=2)
    chat_id = UUID(int=11)
    views = FakeViewRepo()

    result = await ImageCatalogService.pick_for_chat(
        chat_id=chat_id,
        image_repo=FakeImageRepo.with_images(image),
        view_repo=views,
        at=dt(13),
    )

    assert result is image
    assert (chat_id, image.id) in views.shown


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_uses_selectable_min_score() -> None:
    image = mk_image(image_id=6, score=1)
    images = FakeImageRepo.with_images(image)
    chat_id = UUID(int=12)

    result = await ImageCatalogService.pick_for_chat(
        chat_id=chat_id,
        image_repo=images,
        view_repo=FakeViewRepo(),
        at=dt(14),
    )

    assert result is image
    assert ImageScorePolicy.is_selectable(result.score)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_pick_validates_chat_id() -> None:
    with pytest.raises(ValidationError):
        await ImageCatalogService.pick_for_chat(
            chat_id="bad",  # type: ignore[arg-type]
            image_repo=FakeImageRepo(),
            view_repo=FakeViewRepo(),
            at=dt(12),
        )
