"""Тесты ImageRandomService и ImageRandomUseCase."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from dom.image.factories import mk_image

from app.dto import ImageCard
from app.services.image_random import ImageRandomService
from app.use_cases.image_random import ImageRandomUseCase
from domain.kernel.vo import AwareDatetime

from ..factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_returns_none_when_catalog_empty() -> None:
    images = AsyncMock()
    seen = AsyncMock()
    images.get_random_unseen_for_chat.return_value = None
    srv = ImageRandomService(logger=mk_logger())
    chat_id = UUID(int=99)

    result = await srv.pick_for_chat(
        images=images,
        seen=seen,
        chat_id=chat_id,
        at=dt(10),
    )

    assert result is None
    images.get_random_unseen_for_chat.assert_awaited_once_with(chat_id, min_score=1)
    seen.mark_seen.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_marks_seen_and_returns_card() -> None:
    image = mk_image(image_id=3, score=2, created_at=dt(9))
    images = AsyncMock()
    seen = AsyncMock()
    images.get_random_unseen_for_chat.return_value = image
    srv = ImageRandomService(logger=mk_logger())
    chat_id = UUID(int=100)

    result = await srv.pick_for_chat(
        images=images,
        seen=seen,
        chat_id=chat_id,
        at=dt(10),
    )

    assert isinstance(result, ImageCard)
    assert result.id == image.id
    assert result.score == 2
    seen.mark_seen.assert_awaited_once_with(chat_id, image.id, at=dt(10))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_pick_for_chat_runs_in_uow() -> None:
    image = mk_image(image_id=4, score=1, created_at=dt(9))
    images = AsyncMock()
    images.get_random_unseen_for_chat.return_value = image
    uow = FakeUoW(images=images)
    service = AsyncMock()
    service.pick_for_chat.return_value = ImageCard.from_domain(image)
    uc = ImageRandomUseCase(uow=uow, image_random=service, logger=mk_logger())
    chat_id = UUID(int=101)

    got = await uc.pick_for_chat(chat_id=chat_id, at=dt(11))

    assert got is not None
    assert got.id == image.id
    assert uow.enter_count == uow.exit_count == 1
    service.pick_for_chat.assert_awaited_once_with(
        images=images,
        seen=uow.seen,
        chat_id=chat_id,
        at=dt(11),
    )
