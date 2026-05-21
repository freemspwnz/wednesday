"""Filter that requires a minimum number of command arguments."""

from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter, CommandObject
from aiogram.types import Message


class RequireCommandArgs(BaseFilter):
    """Passes when ``command.args`` has enough tokens; injects ``command_args`` list."""

    def __init__(self, min_count: int = 1) -> None:
        self._min_count = min_count

    async def __call__(
        self,
        message: Message,
        command: CommandObject | None = None,
    ) -> bool | dict[str, Any]:
        if command is None:
            return False
        args = (command.args or "").split()
        if len(args) < self._min_count:
            return False
        return {"command_args": args}


class InsufficientCommandArgs(BaseFilter):
    """Passes when the command has fewer than ``min_count`` argument tokens."""

    def __init__(self, min_count: int = 1) -> None:
        self._min_count = min_count

    async def __call__(
        self,
        message: Message,
        command: CommandObject | None = None,
    ) -> bool:
        if command is None:
            return True
        return len((command.args or "").split()) < self._min_count
