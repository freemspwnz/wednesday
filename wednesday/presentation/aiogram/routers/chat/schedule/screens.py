"""Telegram screen edits for the schedule inline menu."""

from typing import Literal

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.dto import ChatContext

from ....messages import chat as chat_msg
from ...utils import safe_callback_answer
from .keyboard import (
    build_clear_confirm_kb,
    build_day_kb,
    build_hours_kb,
    build_main_kb,
    build_minutes_kb,
    build_remove_kb,
    build_slots_kb,
    build_status_kb,
    build_tz_kb,
)

EditStatus = Literal["ok", "noop", "flood"]

_HOUR_MAX = 23


async def close_menu(callback: CallbackQuery) -> None:
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


async def navigate(callback: CallbackQuery, chat: ChatContext, action: str, value: str) -> None:
    """Edit screen first, then ack (so flood can still use an alert toast)."""
    if action == "menu":
        status = await edit_main(callback, chat)
    elif action == "clear" and value == "ask":
        status = await edit_screen(
            callback,
            chat_msg.SCHEDULE_CLEAR_CONFIRM,
            build_clear_confirm_kb(),
        )
    elif action == "clear" and value == "no":
        status = await edit_screen(
            callback,
            chat_msg.SCHEDULE_MENU_TITLE,
            build_slots_kb(),
        )
    else:
        markup = _submenu_markup(action, value, chat)
        if isinstance(callback.message, Message) and callback.message.text == chat_msg.SCHEDULE_CLEAR_CONFIRM:
            status = await edit_screen(callback, chat_msg.SCHEDULE_MENU_TITLE, markup)
        else:
            status = await edit_markup(callback, markup)

    if status == "flood":
        await safe_callback_answer(callback, chat_msg.SCHEDULE_TRY_LATER, show_alert=True)
        return
    await safe_callback_answer(callback)


async def refresh_after_mutation(callback: CallbackQuery, chat: ChatContext) -> None:
    status = await edit_main(callback, chat)
    if status == "flood":
        await safe_callback_answer(callback, chat_msg.SCHEDULE_SAVED_RETRY, show_alert=True)
        return
    await safe_callback_answer(callback)


async def edit_main(callback: CallbackQuery, chat: ChatContext) -> EditStatus:
    return await edit_screen(callback, chat_msg.SCHEDULE_MENU_TITLE, build_main_kb(chat))


async def edit_markup(callback: CallbackQuery, markup: InlineKeyboardMarkup | None) -> EditStatus:
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


async def edit_screen(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> EditStatus:
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


def _submenu_markup(action: str, value: str, chat: ChatContext) -> InlineKeyboardMarkup | None:
    if action == "open":
        return _open_submenu(value, chat)
    if action == "hours":
        return build_hours_kb()
    if action == "mins":
        return _minutes_submenu(value)
    if action == "rmlist":
        return build_remove_kb(chat.schedules)
    return build_slots_kb()


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


def _same_markup(current: InlineKeyboardMarkup | None, desired: InlineKeyboardMarkup) -> bool:
    if current is None:
        return False
    cur = [[b.text for b in row] for row in current.inline_keyboard]
    new = [[b.text for b in row] for row in desired.inline_keyboard]
    return cur == new
