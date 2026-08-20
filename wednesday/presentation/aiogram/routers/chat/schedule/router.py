"""In-chat schedule management via inline keyboard."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.dto import ChatContext
from app.protocols import Logger, RequestScope

from ....messages import chat as chat_msg
from ...utils import run_callback_handler, run_message_handler, safe_callback_answer
from ..mappers import resolve_chat_member
from .data import ScheduleData
from .keyboard import (
    TIMEZONE_PRESETS,
    build_clear_confirm_kb,
    build_day_kb,
    build_hours_kb,
    build_main_kb,
    build_minutes_kb,
    build_remove_kb,
    build_slots_kb,
    build_status_kb,
    build_tz_kb,
    unpack_hhmm,
)

chat_schedule_router = Router(name="chat_schedule")

_GROUP_TYPES = frozenset({"group", "supergroup"})
_WEEKDAY_MIN = 1
_WEEKDAY_MAX = 7
_HOUR_MAX = 23
_MAX_SCHEDULE_SLOTS = 3
_EditStatus = Literal["ok", "noop", "flood"]


@chat_schedule_router.message(Command("schedule"))
async def cmd_schedule(
    message: Message,
    command: CommandObject,
    chat: ChatContext,
    logger: Logger,
) -> None:
    """Show schedule UI in groups; explain private limitation elsewhere."""

    async def _action() -> None:
        args = (command.args or "").split()
        if args and args[0].lower() in {"help", "?"}:
            await message.answer(chat_msg.SCHEDULE_USAGE)
            return
        if chat.type not in _GROUP_TYPES:
            await message.answer(chat_msg.SCHEDULE_PRIVATE_ONLY)
            return
        await message.answer(
            chat_msg.SCHEDULE_MENU_TITLE,
            reply_markup=build_main_kb(chat),
        )

    await run_message_handler(message, logger, _action)


@chat_schedule_router.callback_query(ScheduleData.filter())
async def cb_schedule(
    callback: CallbackQuery,
    callback_data: ScheduleData,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
) -> None:
    """Navigate schedule menu and apply schedule mutations."""

    async def _action() -> None:
        if not isinstance(callback.message, Message):
            await safe_callback_answer(callback)
            return
        if chat.type not in _GROUP_TYPES:
            await safe_callback_answer(callback, chat_msg.SCHEDULE_PRIVATE_ONLY, show_alert=True)
            return

        action = callback_data.action
        value = callback_data.value

        if action == "rmlist" and not chat.schedules:
            await safe_callback_answer(callback, chat_msg.SCHEDULE_NO_SLOTS, show_alert=True)
            return

        if action == "close":
            await _close_menu(callback)
            return

        if action in {"menu", "open", "hours", "mins", "rmlist"} or (action == "clear" and value in {"ask", "no"}):
            await _navigate(callback, chat, action, value)
            return

        if action == "add":
            await _add_slot(callback, bot, scope, chat, value)
            return
        if action == "status":
            await _mutate(callback, lambda: _apply_status(callback, bot, scope, chat, value))
            return
        if action == "day":
            await _mutate(callback, lambda: _apply_day(callback, bot, scope, chat, value))
            return
        if action == "tz":
            await _mutate(callback, lambda: _apply_tz(callback, bot, scope, chat, value))
            return
        if action == "rm":
            await _mutate(callback, lambda: _apply_remove(callback, bot, scope, chat, value))
            return
        if action == "clear" and value == "yes":
            await _mutate(callback, lambda: _apply_clear(callback, bot, scope, chat))
            return
        await safe_callback_answer(callback)

    await run_callback_handler(callback, scope.logger, _action)


async def _close_menu(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await safe_callback_answer(callback)
        return
    try:
        await callback.message.edit_text(chat_msg.SCHEDULE_CLOSED, reply_markup=None)
    except TelegramRetryAfter:
        await safe_callback_answer(callback, chat_msg.SCHEDULE_TRY_LATER, show_alert=True)
        return
    except TelegramBadRequest:
        pass
    await safe_callback_answer(callback)


async def _navigate(
    callback: CallbackQuery,
    chat: ChatContext,
    action: str,
    value: str,
) -> None:
    """Edit screen first, then ack (so flood can still use an alert toast)."""
    if action == "menu":
        status = await _edit_main(callback, chat)
    elif action == "clear" and value == "ask":
        status = await _edit_screen(
            callback,
            chat_msg.SCHEDULE_CLEAR_CONFIRM,
            build_clear_confirm_kb(),
        )
    elif action == "clear" and value == "no":
        status = await _edit_screen(
            callback,
            chat_msg.SCHEDULE_MENU_TITLE,
            build_slots_kb(),
        )
    else:
        if action == "open":
            markup = _open_submenu(value, chat)
        elif action == "hours":
            markup = build_hours_kb()
        elif action == "mins":
            markup = _minutes_submenu(value)
        elif action == "rmlist":
            markup = build_remove_kb(chat.schedules)
        else:
            markup = build_slots_kb()
        # Leaving clear-confirm restores the short title with the submenu.
        if isinstance(callback.message, Message) and callback.message.text == chat_msg.SCHEDULE_CLEAR_CONFIRM:
            status = await _edit_screen(callback, chat_msg.SCHEDULE_MENU_TITLE, markup)
        else:
            status = await _edit_markup(callback, markup)

    if status == "flood":
        await safe_callback_answer(callback, chat_msg.SCHEDULE_TRY_LATER, show_alert=True)
        return
    await safe_callback_answer(callback)


async def _add_slot(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> None:
    slot = unpack_hhmm(value)
    if slot in chat.schedules:
        await safe_callback_answer(callback, chat_msg.SCHEDULE_SLOT_EXISTS, show_alert=True)
        return
    if len(chat.schedules) >= _MAX_SCHEDULE_SLOTS:
        await safe_callback_answer(callback, chat_msg.SCHEDULE_LIMIT_REACHED, show_alert=True)
        return
    await _mutate(callback, lambda: _apply_add(callback, bot, scope, chat, value))


async def _mutate(
    callback: CallbackQuery,
    runner: Callable[[], Awaitable[ChatContext]],
) -> None:
    """Run UC before ack so domain errors can still show an alert toast."""
    updated = await runner()
    status = await _edit_main(callback, updated)
    if status == "flood":
        await safe_callback_answer(callback, chat_msg.SCHEDULE_SAVED_RETRY, show_alert=True)
        return
    await safe_callback_answer(callback)


def _open_submenu(value: str, chat: ChatContext) -> InlineKeyboardMarkup | None:
    if value == "status":
        return build_status_kb(is_active=chat.is_active)
    if value == "day":
        return build_day_kb(current=chat.weekday)
    if value == "tz":
        return build_tz_kb(current=chat.timezone)
    if value == "slots":
        return build_slots_kb()
    return None


def _minutes_submenu(value: str) -> InlineKeyboardMarkup:
    try:
        hour = int(value)
    except ValueError as exc:
        msg = "Некорректный час."
        raise ValueError(msg) from exc
    if hour < 0 or hour > _HOUR_MAX:
        msg = "Некорректный час."
        raise ValueError(msg)
    return build_minutes_kb(hour=hour)


async def _edit_markup(callback: CallbackQuery, markup: InlineKeyboardMarkup | None) -> _EditStatus:
    if not isinstance(callback.message, Message) or markup is None:
        return "noop"
    if _same_markup(callback.message.reply_markup, markup):
        return "noop"
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except TelegramRetryAfter:
        return "flood"
    except TelegramBadRequest:
        return "noop"
    return "ok"


async def _edit_main(callback: CallbackQuery, chat: ChatContext) -> _EditStatus:
    return await _edit_screen(callback, chat_msg.SCHEDULE_MENU_TITLE, build_main_kb(chat))


async def _edit_screen(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> _EditStatus:
    if not isinstance(callback.message, Message) or markup is None:
        return "noop"
    if callback.message.text == text and _same_markup(callback.message.reply_markup, markup):
        return "noop"
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramRetryAfter:
        return "flood"
    except TelegramBadRequest:
        return "noop"
    return "ok"


def _same_markup(current: InlineKeyboardMarkup | None, desired: InlineKeyboardMarkup) -> bool:
    if current is None:
        return False
    cur = [[b.text for b in row] for row in current.inline_keyboard]
    new = [[b.text for b in row] for row in desired.inline_keyboard]
    return cur == new


async def _apply_status(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    if value == "on":
        return await scope.chat_management_uc.activate(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            at=at,
        )
    if value == "off":
        return await scope.chat_management_uc.deactivate(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            at=at,
        )
    msg = "Неизвестное действие для рассылки."
    raise ValueError(msg)


async def _apply_day(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    try:
        weekday = int(value)
    except ValueError as exc:
        msg = "Некорректный день недели."
        raise ValueError(msg) from exc
    if weekday < _WEEKDAY_MIN or weekday > _WEEKDAY_MAX:
        msg = "Некорректный день недели."
        raise ValueError(msg)
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.change_schedule_day(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        new_weekday=weekday,
        at=at,
    )


async def _apply_tz(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    try:
        index = int(value)
        timezone = TIMEZONE_PRESETS[index]
    except (ValueError, IndexError) as exc:
        msg = "Некорректная таймзона."
        raise ValueError(msg) from exc
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.change_schedule_timezone(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        timezone=timezone,
        at=at,
    )


async def _apply_add(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    slot = unpack_hhmm(value)
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.add_schedule(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        schedule=slot,
        at=at,
    )


async def _apply_remove(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    slot = unpack_hhmm(value)
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.remove_schedule(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        schedule=slot,
        at=at,
    )


async def _apply_clear(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
) -> ChatContext:
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.clear_schedules(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        at=at,
    )
