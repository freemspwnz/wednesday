from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, ChatMemberUpdated, Message, TelegramObject, User

from app.dto import ChatContext, UserContext
from app.protocols import Logger

from ..utils import CHAT_MEMBER_LEFT_STATUSES, require_request_scope


class RegistrationMiddleware(BaseMiddleware):
    """Eager registration on all handled updates including chat_member.

    Skips only when the bot is left/kicked from a chat (my_chat_member).
    DTO fields such as is_active are not applied to existing aggregates on register.
    """

    _UPDATE_PAYLOAD_ATTRS: tuple[str, ...] = (
        "message",
        "edited_message",
        "callback_query",
        "my_chat_member",
        "chat_member",
    )

    def __init__(
        self,
        *,
        logger: Logger,
    ) -> None:
        self._logger = logger.bind(module=self.__class__.__name__)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401  # aiogram handler return type
        user: UserContext | None = None
        chat: ChatContext | None = None

        # dp.update.middleware receives Update; handlers see the nested payload.
        payload = self._unwrap_update(event)

        if self._should_skip_registration(payload):
            data["user"] = None
            data["chat"] = None
            return await handler(event, data)

        scope = require_request_scope(data.get("scope"))

        tg_user = self._extract_user(payload)
        tg_chat = self._extract_chat(payload)
        at = self._extract_at(payload)

        if tg_user is not None:
            user = await scope.user_lifecycle_uc.register(
                tg_id=tg_user.id,
                is_bot=tg_user.is_bot,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                username=tg_user.username,
                language_code=tg_user.language_code,
                has_tg_premium=tg_user.is_premium,
                at=at,
            )

        if tg_chat is not None:
            chat = await scope.chat_management_uc.register(
                tg_id=tg_chat.id,
                type=tg_chat.type,
                title=tg_chat.title,
                username=tg_chat.username,
                at=at,
            )

        data["user"] = user
        data["chat"] = chat

        return await handler(event, data)

    @classmethod
    def _unwrap_update(cls, event: TelegramObject) -> TelegramObject:
        """Return nested message/callback/chat_member payload when ``event`` is Update."""
        for attr in cls._UPDATE_PAYLOAD_ATTRS:
            payload = getattr(event, attr, None)
            if isinstance(payload, TelegramObject):
                return payload
        return event

    @staticmethod
    def _should_skip_registration(event: TelegramObject) -> bool:
        """Bot left/kicked from a chat: handler uses find_by_tg_id only, no get_or_create."""
        if not isinstance(event, ChatMemberUpdated):
            return False
        member = event.new_chat_member
        return member.user.is_bot and member.status in CHAT_MEMBER_LEFT_STATUSES

    @staticmethod
    def _extract_user(event: TelegramObject) -> User | None:
        user = getattr(event, "from_user", None)
        if isinstance(user, User):
            return user
        message = getattr(event, "message", None)
        nested = getattr(message, "from_user", None) if message is not None else None
        if isinstance(nested, User):
            return nested
        if isinstance(event, ChatMemberUpdated):
            return event.new_chat_member.user
        return None

    @staticmethod
    def _extract_chat(event: TelegramObject) -> Chat | None:
        chat = getattr(event, "chat", None)
        if isinstance(chat, Chat):
            return chat
        message = getattr(event, "message", None)
        nested = getattr(message, "chat", None) if message is not None else None
        return nested if isinstance(nested, Chat) else None

    @staticmethod
    def _extract_at(event: TelegramObject) -> datetime:
        if isinstance(event, Message | ChatMemberUpdated):
            return event.date
        if isinstance(event, CallbackQuery):
            return datetime.now(UTC)
        date = getattr(event, "date", None)
        if isinstance(date, datetime):
            return date
        return datetime.now(UTC)
