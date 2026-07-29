"""Tests for routers/utils: parsing, membership, run_message_handler."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import CallbackQuery, Message, User as TgUser

from presentation.aiogram.messages.exceptions import COMMAND_FAILURE
from presentation.aiogram.routers.utils import (
    is_bot_member_of_chat,
    parse_positive_int,
    parse_telegram_id,
    run_callback_handler,
    run_message_handler,
)

from ..factories import make_callback_query, make_message


@pytest.mark.unit
def test_parse_telegram_id() -> None:
    assert parse_telegram_id("-1001") == -1001


@pytest.mark.unit
def test_parse_username_rejected() -> None:
    with pytest.raises(ValueError, match="username"):
        parse_telegram_id("@user")


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["7", "1"])
def test_parse_positive_int_ok(raw: str) -> None:
    assert parse_positive_int(raw) == int(raw)


@pytest.mark.unit
def test_parse_positive_int_rejects_zero() -> None:
    with pytest.raises(ValueError, match="не меньше 1"):
        parse_positive_int("0")


@pytest.mark.unit
def test_parse_telegram_id_rejects_non_integer() -> None:
    with pytest.raises(ValueError, match="целочисленный"):
        parse_telegram_id("abc")


@pytest.mark.unit
def test_parse_positive_int_rejects_non_integer() -> None:
    with pytest.raises(ValueError, match="целое число"):
        parse_positive_int("x")


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "forbidden", "expected"),
    [
        (ChatMemberStatus.MEMBER, False, True),
        (ChatMemberStatus.LEFT, False, False),
        (ChatMemberStatus.MEMBER, True, False),
    ],
)
async def test_is_bot_member_of_chat(status: ChatMemberStatus, forbidden: bool, expected: bool) -> None:
    bot = AsyncMock()
    bot.me.return_value = Mock(id=1)
    if forbidden:
        bot.get_chat_member.side_effect = TelegramForbiddenError(method=Mock(), message="forbidden")
    else:
        bot.get_chat_member.return_value = Mock(status=status)

    assert await is_bot_member_of_chat(bot, -100123) is expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_message_handler_success(mock_logger: MagicMock) -> None:
    async def action() -> str:
        return "ok"

    assert await run_message_handler(make_message(), mock_logger, action) == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_message_handler_mapped_error(mock_logger: MagicMock) -> None:
    async def action() -> None:
        raise ValueError("bad id")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await run_message_handler(make_message(), mock_logger, action)
    answer.assert_awaited_once_with("bad id")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_message_handler_fallback(mock_logger: MagicMock) -> None:
    async def action() -> None:
        raise RuntimeError("boom")

    with (
        patch("presentation.aiogram.routers.utils.user_message_for_exception", return_value=None),
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
    ):
        await run_message_handler(make_message(), mock_logger, action)
    answer.assert_awaited_once_with(COMMAND_FAILURE)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_callback_handler_success(mock_logger: MagicMock) -> None:
    callback = make_callback_query(data="test")

    async def action() -> str:
        return "ok"

    assert await run_callback_handler(callback, mock_logger, action) == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_callback_handler_replies_via_alert(mock_logger: MagicMock) -> None:
    callback = make_callback_query(data="test")

    async def action() -> None:
        raise ValueError("bad vote")

    with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer:
        await run_callback_handler(callback, mock_logger, action)
    answer.assert_awaited_once_with("bad vote", show_alert=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_callback_handler_alert_when_no_message(mock_logger: MagicMock) -> None:
    callback = CallbackQuery(
        id="cq2",
        from_user=TgUser(id=1, is_bot=False, first_name="A"),
        chat_instance="test",
        data="imgvote:test",
        message=None,
    )

    async def action() -> None:
        raise RuntimeError("boom")

    with (
        patch("presentation.aiogram.routers.utils.user_message_for_exception", return_value=None),
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
    ):
        await run_callback_handler(callback, mock_logger, action)

    answer.assert_awaited_once_with(COMMAND_FAILURE, show_alert=True)
