"""Тесты aiogram-фильтров presentation-слоя."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.filters import CommandObject
from aiogram.types import Chat, Message, User

from presentation.aiogram.filters import InsufficientCommandArgs, RequireCommandArgs

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def _message() -> Message:
    return Message(
        message_id=1,
        date=_MSG_DATE,
        text="/ban 42 7",
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="A"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("args", "min_count", "expected"),
    [
        ("42 7", 2, {"command_args": ["42", "7"]}),
        ("-1001", 1, {"command_args": ["-1001"]}),
    ],
)
async def test_require_command_args_passes(args: str, min_count: int, expected: dict[str, list[str]]) -> None:
    filt = RequireCommandArgs(min_count=min_count)
    command = CommandObject(prefix="/", command="cmd", args=args)
    assert await filt(_message(), command=command) == expected


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        None,
        CommandObject(prefix="/", command="activate", args=None),
        CommandObject(prefix="/", command="activate", args=""),
    ],
)
async def test_require_command_args_rejects(command: CommandObject | None) -> None:
    assert await RequireCommandArgs()(_message(), command=command) is False


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("args", "min_count", "expected"),
    [
        (None, 1, True),
        ("-1001", 1, False),
        ("42", 2, True),
        ("42 7", 2, False),
    ],
)
async def test_insufficient_command_args(args: str | None, min_count: int, expected: bool) -> None:
    filt = InsufficientCommandArgs(min_count=min_count)
    command = CommandObject(prefix="/", command="ban", args=args)
    assert await filt(_message(), command=command) is expected
