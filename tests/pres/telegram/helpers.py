"""Shared helpers for presentation telegram tests (not pytest fixtures)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType

from aiogram.types import Chat, Message, User

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def make_message(*, text: str = "/cmd", user_id: int = 1, chat_id: int = 1) -> Message:
    return Message(
        message_id=1,
        date=_MSG_DATE,
        text=text,
        chat=Chat(id=chat_id, type="private" if chat_id > 0 else "supergroup"),
        from_user=User(id=user_id, is_bot=False, first_name="A"),
    )


class ScopeCM:
    def __init__(self, scope: object) -> None:
        self._scope = scope

    async def __aenter__(self) -> object:
        return self._scope

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None
