"""Tests for common router handlers."""

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Message

from presentation.aiogram.messages import common as common_msg
from presentation.aiogram.routers import common as handlers

from ..factories import make_message


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "text", "expected"),
    [
        (handlers.cmd_start, "/start", common_msg.WELCOME),
        (handlers.cmd_help, "/help", common_msg.HELP),
        (handlers.cmd_unknown, "/nope", common_msg.UNKNOWN_COMMAND),
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
