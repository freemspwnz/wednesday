"""Tests for common router handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Message

from presentation.aiogram.messages import commands as cmd_msg
from presentation.aiogram.routers import common as handlers

from ..factories import make_message


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "text", "expected"),
    [
        (handlers.cmd_start, "/start", cmd_msg.WELCOME),
        (handlers.cmd_help, "/help", cmd_msg.HELP),
        (handlers.cmd_unknown, "/nope", cmd_msg.UNKNOWN_COMMAND),
    ],
)
async def test_common_commands(
    handler: object,
    text: str,
    expected: str,
    mock_logger: object,
) -> None:
    message = make_message(text=text)
    with patch.object(Message, "reply", new_callable=AsyncMock) as reply:
        await handler(message, mock_logger)  # type: ignore[operator]
    reply.assert_awaited_once_with(text=expected)
