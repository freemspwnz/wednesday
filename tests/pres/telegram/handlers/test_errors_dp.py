"""Integration: dp.errors handler."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.types import Chat, Message, TelegramObject, Update, User

from app.exceptions import AppError
from domain.kernel.exceptions import ValidationError
from presentation.aiogram.messages.exceptions import SERVER_ERROR
from presentation.aiogram.routers.errors import error_handler, send_text_to_update

from ..factories import make_message

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def _update() -> Update:
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=_MSG_DATE,
            text="/boom",
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="A"),
        ),
    )


class _LoggerMW(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["logger"] = MagicMock()
        return await handler(event, data)


async def _feed_with(exc: BaseException) -> AsyncMock:
    dp = Dispatcher()
    router = Router(name="probe")

    @router.message()
    async def probe(_: Message) -> None:
        raise exc

    dp.include_router(router)
    dp.errors.register(error_handler)
    dp.errors.middleware(_LoggerMW())
    dp.update.middleware(_LoggerMW())

    answer = AsyncMock()
    with patch.object(Message, "answer", answer):
        await dp.feed_update(AsyncMock(spec=Bot), _update())
    return answer


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ValidationError("bad input"), "bad input"),
        (RuntimeError("unexpected"), SERVER_ERROR),
        (AppError("app layer"), "app layer"),
    ],
)
async def test_dp_errors_replies(exc: BaseException, expected: str) -> None:
    answer = await _feed_with(exc)
    answer.assert_awaited_once_with(expected)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_text_to_message() -> None:
    answer = AsyncMock()
    update = Update(update_id=1, message=make_message(text="x"))
    with patch.object(Message, "answer", answer):
        assert await send_text_to_update(update, "hi") is True
    answer.assert_awaited_once_with("hi")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_text_unsupported_update() -> None:
    assert await send_text_to_update(Update(update_id=1), "x") is False
