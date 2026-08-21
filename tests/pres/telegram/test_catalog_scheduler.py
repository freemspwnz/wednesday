"""Tests for in-process catalog schedule delivery."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError

from app.dto import ImageCard
from domain.kernel.vo import AwareDatetime
from presentation.aiogram.messages import image as image_msg
from presentation.aiogram.scheduler.catalog import CatalogScheduleRunner
from tests.dom.image.factories import mk_image

from .factories import ScopeCM, mk_chat_context

_WED_NOON_DT = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)
_WED_NOON = AwareDatetime(_WED_NOON_DT)


def _runner(
    *,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    bot: AsyncMock | None = None,
) -> tuple[CatalogScheduleRunner, AsyncMock]:
    resolved_bot = bot or AsyncMock()
    factory = MagicMock(return_value=ScopeCM(mock_scope))
    runner = CatalogScheduleRunner(bot=resolved_bot, scope_factory=factory, logger=mock_logger)
    return runner, resolved_bot


@pytest.mark.unit
def test_seconds_until_next_minute_aligns_to_boundary() -> None:
    now = datetime(2026, 1, 7, 12, 0, 40, tzinfo=UTC)
    assert CatalogScheduleRunner._seconds_until_next_minute(now) == 20.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_advances_wall_clock_across_iterations(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    t0 = datetime(2026, 1, 7, 12, 0, 40, tzinfo=UTC)
    t1 = datetime(2026, 1, 7, 12, 1, 5, tzinfo=UTC)
    mock_scope.chat_schedule_uc.list_due = AsyncMock(return_value=[])
    runner, _ = _runner(mock_scope=mock_scope, mock_logger=mock_logger)

    tick_ats: list[datetime] = []
    sleep_seconds: list[float] = []
    real_tick = runner.tick

    async def spy_tick(*, at: datetime) -> None:
        tick_ats.append(at)
        await real_tick(at=at)

    async def fake_sleep(seconds: float) -> None:
        sleep_seconds.append(seconds)
        if len(sleep_seconds) >= 2:
            raise asyncio.CancelledError

    with (
        patch.object(runner, "tick", side_effect=spy_tick),
        patch(
            "presentation.aiogram.scheduler.catalog.datetime",
            wraps=datetime,
        ) as mock_dt,
        patch(
            "presentation.aiogram.scheduler.catalog.asyncio.sleep",
            side_effect=fake_sleep,
        ),
    ):
        mock_dt.now.side_effect = [t0, t1]
        with pytest.raises(asyncio.CancelledError):
            await runner.run()

    assert tick_ats == [t0, t1]
    assert sleep_seconds == [20.0, 55.0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tick_sends_unseen_catalog_photo(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    chat = mk_chat_context(tg_id=-1001)
    card = ImageCard.from_domain(mk_image(image_id=11))
    mock_scope.chat_schedule_uc.list_due = AsyncMock(return_value=[chat])
    mock_scope.image_catalog_uc.pick_for_chat = AsyncMock(return_value=card)
    runner, bot = _runner(mock_scope=mock_scope, mock_logger=mock_logger)

    await runner.tick(at=_WED_NOON_DT)

    mock_scope.chat_schedule_uc.list_due.assert_awaited_once_with(at=_WED_NOON_DT)
    mock_scope.image_catalog_uc.pick_for_chat.assert_awaited_once_with(chat_id=chat.id)
    bot.send_photo.assert_awaited_once()
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs["chat_id"] == chat.tg_id
    assert kwargs["photo"] == str(card.file_id)
    assert kwargs["reply_markup"] is not None
    mock_scope.image_catalog_uc.mark_shown.assert_awaited_once_with(
        chat_id=chat.id,
        image_id=card.id,
        at=_WED_NOON_DT,
    )
    mock_scope.image_generation_uc.generate.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tick_sends_notice_when_catalog_empty(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    chat = mk_chat_context(tg_id=-1001)
    mock_scope.chat_schedule_uc.list_due = AsyncMock(return_value=[chat])
    mock_scope.image_catalog_uc.pick_for_chat = AsyncMock(return_value=None)
    runner, bot = _runner(mock_scope=mock_scope, mock_logger=mock_logger)

    await runner.tick(at=_WED_NOON_DT)
    await runner.tick(at=_WED_NOON_DT)

    bot.send_photo.assert_not_called()
    bot.send_message.assert_awaited_once_with(
        chat_id=chat.tg_id,
        text=image_msg.SCHEDULE_CATALOG_EMPTY,
    )
    mock_scope.image_catalog_uc.mark_shown.assert_not_awaited()
    assert mock_scope.image_catalog_uc.pick_for_chat.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tick_does_not_send_twice_in_the_same_minute(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    chat = mk_chat_context(tg_id=-1001)
    card = ImageCard.from_domain(mk_image())
    mock_scope.chat_schedule_uc.list_due = AsyncMock(return_value=[chat])
    mock_scope.image_catalog_uc.pick_for_chat = AsyncMock(return_value=card)
    runner, bot = _runner(mock_scope=mock_scope, mock_logger=mock_logger)

    await runner.tick(at=_WED_NOON_DT)
    await runner.tick(at=_WED_NOON_DT)

    bot.send_photo.assert_awaited_once()
    assert mock_scope.image_catalog_uc.pick_for_chat.await_count == 1
    assert mock_scope.image_catalog_uc.mark_shown.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tick_send_error_does_not_mark_shown_or_retry(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    chat = mk_chat_context(tg_id=-1001)
    card = ImageCard.from_domain(mk_image())
    mock_scope.chat_schedule_uc.list_due = AsyncMock(return_value=[chat])
    mock_scope.image_catalog_uc.pick_for_chat = AsyncMock(return_value=card)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(
        side_effect=TelegramForbiddenError(method=MagicMock(), message="kicked"),
    )
    runner, _ = _runner(mock_scope=mock_scope, mock_logger=mock_logger, bot=bot)

    await runner.tick(at=_WED_NOON_DT)
    await runner.tick(at=_WED_NOON_DT)

    assert bot.send_photo.await_count == 1
    mock_scope.image_catalog_uc.mark_shown.assert_not_awaited()
    assert mock_scope.image_catalog_uc.pick_for_chat.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tick_send_error_does_not_block_next_chat(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    failing = mk_chat_context(tg_id=-1001, domain_id=1)
    ok = mk_chat_context(tg_id=-1002, domain_id=2)
    card = ImageCard.from_domain(mk_image())
    mock_scope.chat_schedule_uc.list_due = AsyncMock(return_value=[failing, ok])
    mock_scope.image_catalog_uc.pick_for_chat = AsyncMock(return_value=card)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(
        side_effect=[
            TelegramForbiddenError(method=MagicMock(), message="kicked"),
            MagicMock(),
        ],
    )
    runner, _ = _runner(mock_scope=mock_scope, mock_logger=mock_logger, bot=bot)

    await runner.tick(at=_WED_NOON_DT)

    assert bot.send_photo.await_count == 2
    assert bot.send_photo.await_args.kwargs["chat_id"] == ok.tg_id
    mock_scope.image_catalog_uc.mark_shown.assert_awaited_once_with(
        chat_id=ok.id,
        image_id=card.id,
        at=_WED_NOON_DT,
    )
