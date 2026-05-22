"""Utils for aiogram middlewares."""

from typing import TypeGuard

from aiogram.enums import ChatMemberStatus

from app.protocols import RequestScope

CHAT_MEMBER_LEFT_STATUSES = frozenset({ChatMemberStatus.KICKED, ChatMemberStatus.LEFT})


def is_chat(chat_id: int | str) -> bool:
    """Return whether the id is a group/supergroup/channel chat id.

    Any string is treated as a Telegram chat identifier.
    """
    return (isinstance(chat_id, int) and chat_id < 0) or isinstance(chat_id, str)


def is_request_scope(scope: object) -> TypeGuard[RequestScope]:
    return (
        hasattr(scope, "registration_uc")
        and hasattr(scope, "user_commands_uc")
        and hasattr(scope, "chat_commands_uc")
        and hasattr(scope, "logger")
    )


def require_request_scope(scope: object | None) -> RequestScope:
    if scope is None:
        msg = "Request scope is missing in middleware data"
        raise RuntimeError(msg)
    if not is_request_scope(scope):
        msg = "Invalid request scope in middleware data"
        raise TypeError(msg)
    return scope
