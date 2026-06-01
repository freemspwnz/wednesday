"""Tests for chat router (events and schedule commands)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import CommandObject
from aiogram.types import (
    Chat,
    ChatMember as TgChatMember,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    User,
)

from domain.chat import AccessDeniedError, ChatMember, ChatMemberId, ChatMemberRole, Weekday
from domain.kernel.exceptions import InvalidStateTransitionError
from presentation.aiogram.messages import chat as chat_msg, exceptions as exc_msg
from presentation.aiogram.routers.chat import router as h

from ..factories import make_message

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def _event(
    *,
    status: ChatMemberStatus,
    is_bot: bool = False,
    chat_type: str = "supergroup",
) -> ChatMemberUpdated:
    member_user = User(id=1 if is_bot else 5, is_bot=is_bot, first_name="U")
    new_member: TgChatMember
    if status == ChatMemberStatus.MEMBER:
        new_member = ChatMemberMember(user=member_user, status=ChatMemberStatus.MEMBER)
    elif status == ChatMemberStatus.LEFT:
        new_member = ChatMemberLeft(user=member_user, status=ChatMemberStatus.LEFT)
    else:
        new_member = ChatMemberBanned(
            user=member_user, status=ChatMemberStatus.KICKED, until_date=datetime(1970, 1, 1, tzinfo=UTC)
        )
    return ChatMemberUpdated(
        chat=Chat(id=-100, type=chat_type),
        from_user=User(id=99, is_bot=False, first_name="Admin"),
        date=_MSG_DATE,
        old_chat_member=ChatMemberMember(user=member_user, status=ChatMemberStatus.MEMBER),
        new_chat_member=new_member,
    )


def _member_actor(chat_context: object, *, role: ChatMemberRole = ChatMemberRole.ADMIN) -> ChatMember:
    return ChatMember(
        id=ChatMemberId(1),
        role=role,
        chat_id=chat_context.id,  # type: ignore[attr-defined]
    )


def _answer_text(answer: AsyncMock) -> str:
    call = answer.await_args
    assert call is not None
    if call.args:
        return str(call.args[0])
    return str(call.kwargs.get("text", ""))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_left_deactivates(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: object,
) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    await h.on_my_chat_member(_event(status=ChatMemberStatus.LEFT, is_bot=True), AsyncMock(), mock_logger, mock_scope)
    mock_scope.chat_commands_uc.deactivate.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_invalid_transition(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    chat_context: object,
) -> None:
    mock_scope.registration_uc.find_chat_by_tg_id.return_value = chat_context
    mock_scope.chat_commands_uc.deactivate.side_effect = InvalidStateTransitionError("already")
    await h.on_my_chat_member(_event(status=ChatMemberStatus.LEFT, is_bot=True), AsyncMock(), mock_logger, mock_scope)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_joined_sends_welcome(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    await h.on_my_chat_member(_event(status=ChatMemberStatus.MEMBER, is_bot=True), bot, mock_logger, MagicMock())
    bot.send_message.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chat_member_messages(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    await h.on_chat_member(_event(status=ChatMemberStatus.MEMBER), bot, mock_logger)
    await h.on_chat_member(_event(status=ChatMemberStatus.LEFT), bot, mock_logger)
    assert bot.send_message.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_forbidden_send_logged(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=TelegramForbiddenError(method=MagicMock(), message="no"))
    await h.on_my_chat_member(_event(status=ChatMemberStatus.MEMBER, is_bot=True), bot, mock_logger, MagicMock())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chat_member_skips_greetings_in_private(mock_logger: MagicMock) -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    await h.on_chat_member(_event(status=ChatMemberStatus.MEMBER, chat_type="private"), bot, mock_logger)

    bot.send_message.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_shows_context_without_actor_check(
    chat_context: object,
    mock_logger: MagicMock,
) -> None:
    message = make_message(text="/schedule", chat_id=-1001)
    command = CommandObject(prefix="/", command="schedule", args=None)

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_schedule(message, command, chat_context, mock_logger)

    answer.assert_awaited_once()
    assert "Расписание чата" in _answer_text(answer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_help(
    chat_context: object,
    mock_logger: MagicMock,
) -> None:
    message = make_message(text="/schedule help", chat_id=-1001)
    command = CommandObject(prefix="/", command="schedule", args="help")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_schedule(message, command, chat_context, mock_logger)

    answer.assert_awaited_once_with(chat_msg.SCHEDULE_USAGE)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "usage_text"),
    [
        (h.cmd_schedule_add_usage, chat_msg.SCHEDULE_ADD_USAGE),
        (h.cmd_schedule_remove_usage, chat_msg.SCHEDULE_REMOVE_USAGE),
        (h.cmd_schedule_day_usage, chat_msg.SCHEDULE_DAY_USAGE),
        (h.cmd_schedule_tz_usage, chat_msg.SCHEDULE_TZ_USAGE),
    ],
)
async def test_schedule_usage_handlers(handler: object, usage_text: str) -> None:
    message = make_message()
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handler(message)  # type: ignore[operator]
    answer.assert_awaited_once_with(usage_text)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_add_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    from dom.chat.factories import mk_chat

    updated = mk_chat(chat_id=10, telegram_id=-1001)
    mock_scope.chat_commands_uc.add_schedule = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_add 09:30", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=_member_actor(chat_context),
        ),
    ):
        await h.cmd_schedule_add(message, ["09:30"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_commands_uc.add_schedule.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_add_denied_by_domain_policy(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_scope.chat_commands_uc.add_schedule = AsyncMock(side_effect=AccessDeniedError("not_enough_rights"))
    message = make_message(text="/schedule_add 09:30", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=_member_actor(chat_context, role=ChatMemberRole.MEMBER),
        ),
    ):
        await h.cmd_schedule_add(message, ["09:30"], chat_context, bot, mock_scope, mock_logger)

    answer.assert_awaited_once_with(exc_msg.INSUFFICIENT_PERMISSIONS)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_remove_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    from dom.chat.factories import mk_chat

    updated = mk_chat(chat_id=10, telegram_id=-1001)
    mock_scope.chat_commands_uc.remove_schedule = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_remove 09:30", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=_member_actor(chat_context),
        ),
    ):
        await h.cmd_schedule_remove(message, ["09:30"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_commands_uc.remove_schedule.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_clear_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    from dom.chat.factories import mk_chat

    updated = mk_chat(chat_id=10, telegram_id=-1001)
    mock_scope.chat_commands_uc.clear_schedules = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_clear", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=_member_actor(chat_context),
        ),
    ):
        await h.cmd_schedule_clear(message, chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_commands_uc.clear_schedules.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_day_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    from dom.chat.factories import mk_chat

    updated = mk_chat(chat_id=10, telegram_id=-1001)
    mock_scope.chat_commands_uc.change_schedule_day = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_day wed", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=_member_actor(chat_context),
        ),
    ):
        await h.cmd_schedule_day(message, ["wed"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_commands_uc.change_schedule_day.assert_awaited_once()
    call = mock_scope.chat_commands_uc.change_schedule_day.await_args
    assert call is not None
    assert call.kwargs["new_weekday"] == Weekday.WEDNESDAY
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_tz_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    from dom.chat.factories import mk_chat

    updated = mk_chat(chat_id=10, telegram_id=-1001)
    mock_scope.chat_commands_uc.change_schedule_timezone = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_tz Europe/Moscow", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=_member_actor(chat_context),
        ),
    ):
        await h.cmd_schedule_tz(message, ["Europe/Moscow"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_commands_uc.change_schedule_timezone.assert_awaited_once()
    call = mock_scope.chat_commands_uc.change_schedule_timezone.await_args
    assert call is not None
    assert call.kwargs["timezone"] == ZoneInfo("Europe/Moscow")
    answer.assert_awaited_once()
