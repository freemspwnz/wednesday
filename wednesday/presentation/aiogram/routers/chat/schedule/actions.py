"""Decode schedule callbacks and call chat use cases."""

from datetime import UTC, datetime

from aiogram import Bot
from aiogram.types import CallbackQuery

from app.dto import ChatContext
from app.protocols import RequestScope

from ....messages import chat as chat_msg
from ..mappers import resolve_chat_member
from .keyboard import TIMEZONE_PRESETS, unpack_hhmm

_WEEKDAY_MIN = 1
_WEEKDAY_MAX = 7


async def apply_action(  # noqa: PLR0913
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    *,
    action: str,
    value: str,
) -> ChatContext:
    """Map callback action/value to a mutating use case. Raises on invalid payload."""
    if action == "add":
        return await _add(callback, bot, scope, chat, value)
    if action == "status":
        return await _status(callback, bot, scope, chat, value)
    if action == "day":
        return await _day(callback, bot, scope, chat, value)
    if action == "tz":
        return await _tz(callback, bot, scope, chat, value)
    if action == "rm":
        return await _remove(callback, bot, scope, chat, value)
    if action == "clear" and value == "yes":
        return await _clear(callback, bot, scope, chat)
    msg = "Неизвестное действие расписания."
    raise ValueError(msg)


async def _add(
    callback: CallbackQuery,
    bot: Bot,
    scope: RequestScope,
    chat: ChatContext,
    value: str,
) -> ChatContext:
    slot = unpack_hhmm(value)
    if slot in chat.schedules:
        raise ValueError(chat_msg.SCHEDULE_SLOT_EXISTS)
    at = datetime.now(UTC)
    actor_id, actor_role = await resolve_chat_member(bot, callback, chat)
    return await scope.chat_schedule_uc.add_schedule(
        chat_id=chat.id,
        actor_id=actor_id,
        actor_role=actor_role,
        schedule=slot,
        at=at,
    )


async def _status(
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


async def _day(
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


async def _tz(
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


async def _remove(
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


async def _clear(
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
