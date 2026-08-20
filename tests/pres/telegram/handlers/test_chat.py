"""Tests for chat router (events and schedule commands)."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import CommandObject
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMember as TgChatMember,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    User,
)

from domain.chat import AccessDeniedError
from presentation.aiogram.messages import chat as chat_msg, exceptions as exc_msg
from presentation.aiogram.routers import chat as h
from presentation.aiogram.routers.chat.schedule import ScheduleData
from presentation.aiogram.routers.chat.schedule.keyboard import pack_hhmm

from ..factories import make_callback_query, make_message, mk_chat_context

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


def _answer_text(answer: AsyncMock) -> str:
    call = answer.await_args
    assert call is not None
    if call.args:
        return str(call.args[0])
    return str(call.kwargs.get("text", ""))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_left_calls_on_bot_kicked(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    await h.on_my_chat_member(_event(status=ChatMemberStatus.LEFT, is_bot=True), AsyncMock(), mock_logger, mock_scope)
    mock_scope.chat_management_uc.on_bot_kicked.assert_awaited_once_with(tg_id=-100, at=_MSG_DATE)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_my_chat_member_invalid_transition(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    from domain.kernel.exceptions import InvalidStateTransitionError

    mock_scope.chat_management_uc.on_bot_kicked.side_effect = InvalidStateTransitionError("already")
    with pytest.raises(InvalidStateTransitionError):
        await h.on_my_chat_member(
            _event(status=ChatMemberStatus.LEFT, is_bot=True), AsyncMock(), mock_logger, mock_scope
        )


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
async def test_cmd_schedule_shows_context_with_inline_kb(
    chat_context: object,
    mock_logger: MagicMock,
) -> None:
    message = make_message(text="/schedule", chat_id=-1001)
    command = CommandObject(prefix="/", command="schedule", args=None)

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_schedule(message, command, chat_context, mock_logger)

    answer.assert_awaited_once()
    assert "Расписание чата" in _answer_text(answer)
    call = answer.await_args
    assert call is not None
    assert call.kwargs.get("reply_markup") is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_private_explains_group_only(
    mock_logger: MagicMock,
) -> None:
    from domain.chat import ChatType

    private = mk_chat_context(tg_id=42, chat_type=ChatType.PRIVATE, domain_id=11)
    message = make_message(text="/schedule", chat_id=42)
    command = CommandObject(prefix="/", command="schedule", args=None)

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await h.cmd_schedule(message, command, private, mock_logger)

    answer.assert_awaited_once_with(chat_msg.SCHEDULE_PRIVATE_ONLY)


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
async def test_cb_schedule_opens_day_submenu(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    callback = make_callback_query(
        data=ScheduleData(action="open", value="day").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock) as edit,
    ):
        await h.cb_schedule(callback, callback_data, chat_context, bot, mock_scope)

    edit.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_opens_hours_picker(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    callback = make_callback_query(
        data=ScheduleData(action="hours").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock) as edit,
    ):
        await h.cb_schedule(callback, callback_data, chat_context, bot, mock_scope)

    edit.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_adds_slot_via_hhmm(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    updated = replace(mk_chat_context(tg_id=-1001), schedules=[(9, 30)])
    mock_scope.chat_schedule_uc.add_schedule = AsyncMock(return_value=updated)
    callback = make_callback_query(
        data=ScheduleData(action="add", value=pack_hhmm(9, 30)).pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock),
        patch.object(Message, "edit_text", new_callable=AsyncMock),
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cb_schedule(callback, callback_data, chat_context, bot, mock_scope)

    mock_scope.chat_schedule_uc.add_schedule.assert_awaited_once()
    call = mock_scope.chat_schedule_uc.add_schedule.await_args
    assert call is not None
    assert call.kwargs["schedule"] == (9, 30)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_removes_slot(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    with_slot = replace(mk_chat_context(tg_id=-1001), schedules=[(12, 0)])
    updated = replace(with_slot, schedules=[])
    mock_scope.chat_schedule_uc.remove_schedule = AsyncMock(return_value=updated)
    callback = make_callback_query(
        data=ScheduleData(action="rm", value=pack_hhmm(12, 0)).pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock),
        patch.object(Message, "edit_text", new_callable=AsyncMock),
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cb_schedule(callback, callback_data, with_slot, bot, mock_scope)

    mock_scope.chat_schedule_uc.remove_schedule.assert_awaited_once()
    call = mock_scope.chat_schedule_uc.remove_schedule.await_args
    assert call is not None
    assert call.kwargs["schedule"] == (12, 0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_rmlist_empty_toasts(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    callback = make_callback_query(
        data=ScheduleData(action="rmlist").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_reply_markup", new_callable=AsyncMock) as edit,
    ):
        await h.cb_schedule(callback, callback_data, chat_context, bot, mock_scope)

    edit.assert_not_awaited()
    answer.assert_awaited_once_with(chat_msg.SCHEDULE_NO_SLOTS, show_alert=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_clears_slots_on_confirm(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    with_slot = replace(mk_chat_context(tg_id=-1001), schedules=[(9, 0)])
    updated = replace(with_slot, schedules=[])
    mock_scope.chat_schedule_uc.clear_schedules = AsyncMock(return_value=updated)
    callback = make_callback_query(
        data=ScheduleData(action="clear", value="yes").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock),
        patch.object(Message, "edit_text", new_callable=AsyncMock),
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cb_schedule(callback, callback_data, with_slot, bot, mock_scope)

    mock_scope.chat_schedule_uc.clear_schedules.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_sets_day_and_refreshes_main(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    updated = replace(mk_chat_context(tg_id=-1001), weekday=5)
    mock_scope.chat_schedule_uc.change_schedule_day = AsyncMock(return_value=updated)
    callback = make_callback_query(
        data=ScheduleData(action="day", value="5").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_text", new_callable=AsyncMock) as edit,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cb_schedule(callback, callback_data, chat_context, bot, mock_scope)

    mock_scope.chat_schedule_uc.change_schedule_day.assert_awaited_once()
    call = mock_scope.chat_schedule_uc.change_schedule_day.await_args
    assert call is not None
    assert call.kwargs["new_weekday"] == 5
    edit.assert_awaited_once()
    assert edit.await_args is not None
    assert edit.await_args.kwargs.get("reply_markup") is not None
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_sets_timezone(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    updated = replace(mk_chat_context(tg_id=-1001), timezone="Europe/Moscow")
    mock_scope.chat_schedule_uc.change_schedule_timezone = AsyncMock(return_value=updated)
    callback = make_callback_query(
        data=ScheduleData(action="tz", value="1").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock),
        patch.object(Message, "edit_text", new_callable=AsyncMock),
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cb_schedule(callback, callback_data, chat_context, bot, mock_scope)

    mock_scope.chat_schedule_uc.change_schedule_timezone.assert_awaited_once()
    call = mock_scope.chat_schedule_uc.change_schedule_timezone.await_args
    assert call is not None
    assert call.kwargs["timezone"] == "Europe/Moscow"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_activates_broadcast(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    inactive = replace(mk_chat_context(tg_id=-1001), is_active=False)
    updated = replace(inactive, is_active=True)
    mock_scope.chat_management_uc.activate = AsyncMock(return_value=updated)
    callback = make_callback_query(
        data=ScheduleData(action="status", value="on").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock),
        patch.object(Message, "edit_text", new_callable=AsyncMock),
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cb_schedule(callback, callback_data, inactive, bot, mock_scope)

    mock_scope.chat_management_uc.activate.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cb_schedule_day_denied_by_domain_policy(
    chat_context: object,
    mock_scope: MagicMock,
) -> None:
    mock_scope.chat_schedule_uc.change_schedule_day = AsyncMock(
        side_effect=AccessDeniedError("not_enough_rights"),
    )
    callback = make_callback_query(
        data=ScheduleData(action="day", value="1").pack(),
        chat_id=-1001,
    )
    callback_data = ScheduleData.unpack(callback.data or "")
    bot = AsyncMock()

    with (
        patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer,
        patch.object(Message, "edit_text", new_callable=AsyncMock) as edit,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "member"),
        ),
    ):
        await h.cb_schedule(callback, callback_data, chat_context, bot, mock_scope)

    edit.assert_not_awaited()
    answer.assert_awaited_once_with(exc_msg.INSUFFICIENT_PERMISSIONS, show_alert=True)


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
    updated = mk_chat_context(tg_id=-1001)
    mock_scope.chat_schedule_uc.add_schedule = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_add 09:30", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cmd_schedule_add(message, ["09:30"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_schedule_uc.add_schedule.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_add_denied_by_domain_policy(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_scope.chat_schedule_uc.add_schedule = AsyncMock(side_effect=AccessDeniedError("not_enough_rights"))
    message = make_message(text="/schedule_add 09:30", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "member"),
        ),
    ):
        await h.cmd_schedule_add(message, ["09:30"], chat_context, bot, mock_scope, mock_logger)

    answer.assert_awaited_once_with(exc_msg.INSUFFICIENT_PERMISSIONS)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_activate_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    updated = mk_chat_context(tg_id=-1001)
    mock_scope.chat_management_uc.activate = AsyncMock(return_value=updated)
    message = make_message(text="/activate", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.management.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cmd_activate(message, chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_management_uc.activate.assert_awaited_once()
    answer.assert_awaited_once()
    assert "активна" in _answer_text(answer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_deactivate_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    updated = replace(mk_chat_context(tg_id=-1001), is_active=False)
    mock_scope.chat_management_uc.deactivate = AsyncMock(return_value=updated)
    message = make_message(text="/deactivate", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.management.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cmd_deactivate(message, chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_management_uc.deactivate.assert_awaited_once()
    answer.assert_awaited_once()
    assert "приостановлена" in _answer_text(answer)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_activate_denied_by_domain_policy(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_scope.chat_management_uc.activate = AsyncMock(side_effect=AccessDeniedError("not_enough_rights"))
    message = make_message(text="/activate", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.management.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "member"),
        ),
    ):
        await h.cmd_activate(message, chat_context, bot, mock_scope, mock_logger)

    answer.assert_awaited_once_with(exc_msg.INSUFFICIENT_PERMISSIONS)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_remove_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    updated = mk_chat_context(tg_id=-1001)
    mock_scope.chat_schedule_uc.remove_schedule = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_remove 09:30", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cmd_schedule_remove(message, ["09:30"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_schedule_uc.remove_schedule.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_clear_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    updated = mk_chat_context(tg_id=-1001)
    mock_scope.chat_schedule_uc.clear_schedules = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_clear", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cmd_schedule_clear(message, chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_schedule_uc.clear_schedules.assert_awaited_once()
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_day_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    updated = mk_chat_context(tg_id=-1001)
    mock_scope.chat_schedule_uc.change_schedule_day = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_day wed", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cmd_schedule_day(message, ["wed"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_schedule_uc.change_schedule_day.assert_awaited_once()
    call = mock_scope.chat_schedule_uc.change_schedule_day.await_args
    assert call is not None
    assert call.kwargs["new_weekday"] == 3
    answer.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_schedule_tz_calls_uc(
    chat_context: object,
    mock_scope: MagicMock,
    mock_logger: MagicMock,
) -> None:
    updated = mk_chat_context(tg_id=-1001)
    mock_scope.chat_schedule_uc.change_schedule_timezone = AsyncMock(return_value=updated)
    message = make_message(text="/schedule_tz Europe/Moscow", chat_id=-1001)
    bot = AsyncMock()

    with (
        patch.object(Message, "answer", new_callable=AsyncMock) as answer,
        patch(
            "presentation.aiogram.routers.chat.schedule.router.resolve_chat_member",
            new_callable=AsyncMock,
            return_value=(1, "admin"),
        ),
    ):
        await h.cmd_schedule_tz(message, ["Europe/Moscow"], chat_context, bot, mock_scope, mock_logger)

    mock_scope.chat_schedule_uc.change_schedule_timezone.assert_awaited_once()
    call = mock_scope.chat_schedule_uc.change_schedule_timezone.await_args
    assert call is not None
    assert call.kwargs["timezone"] == "Europe/Moscow"
    answer.assert_awaited_once()
