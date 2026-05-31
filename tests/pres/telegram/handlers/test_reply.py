"""Tests for send_text_to_update."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Chat, Message, Update, User

from presentation.aiogram.routers.error import send_text_to_update

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_text_to_message() -> None:
    answer = AsyncMock()
    update = Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=_MSG_DATE,
            text="x",
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="A"),
        ),
    )

    with patch.object(Message, "answer", answer):
        assert await send_text_to_update(update, "hi") is True

    answer.assert_awaited_once_with("hi")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_text_unsupported_update() -> None:
    assert await send_text_to_update(Update(update_id=1), "x") is False
