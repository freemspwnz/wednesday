from collections.abc import Awaitable, Callable
from typing import Any, Literal

from aiogram import BaseMiddleware
from aiogram.types import Chat, ChatMemberUpdated, TelegramObject, User

from app.dto import ChatContext, UserContext
from app.protocols import Logger
from domain.chat import ChatType
from domain.kernel.vo import NonEmptyStr

from ..utils import CHAT_MEMBER_LEFT_STATUSES, require_request_scope


class RegistrationMiddleware(BaseMiddleware):
    """Eager registration on all handled updates including chat_member.

    Skips only when the bot is left/kicked from a chat (my_chat_member).
    DTO fields such as is_active are not applied to existing aggregates on reg_user/reg_chat.
    """

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

        if self._should_skip_registration(event):
            data["user"] = None
            data["chat"] = None
            return await handler(event, data)

        request_scope = require_request_scope(data.get("scope"))

        tg_user = self._extract_user(event)
        tg_chat = self._extract_chat(event)

        if tg_user is not None:
            user = self._to_user_ctx(tg_user)
            user = await request_scope.registration_uc.reg_user(dto=user)

        if tg_chat is not None:
            chat = self._to_chat_ctx(tg_chat)
            chat = await request_scope.registration_uc.reg_chat(dto=chat)

        data["user"] = user
        data["chat"] = chat

        return await handler(event, data)

    @staticmethod
    def _should_skip_registration(event: TelegramObject) -> bool:
        """Bot left/kicked from chat: handler uses find_chat only, no get_or_create."""
        if not isinstance(event, ChatMemberUpdated):
            return False
        member = event.new_chat_member
        return member.user.is_bot and member.status in CHAT_MEMBER_LEFT_STATUSES

    def _extract_user(self, event: TelegramObject) -> User | None:
        entity = self._extract_entity(entity_type="user", event=event)
        return entity if isinstance(entity, User) else None

    def _extract_chat(self, event: TelegramObject) -> Chat | None:
        entity = self._extract_entity(entity_type="chat", event=event)
        return entity if isinstance(entity, Chat) else None

    @staticmethod
    def _extract_entity(
        *,
        entity_type: Literal["user", "chat"],
        event: TelegramObject,
    ) -> User | Chat | None:
        if entity_type == "chat":
            direct_chat = getattr(event, "chat", None)
            if isinstance(direct_chat, Chat):
                return direct_chat

        if entity_type == "user":
            direct_user = getattr(event, "from_user", None)
            if isinstance(direct_user, User):
                return direct_user

        if entity_type == "user":
            search = "from_user"
        else:
            search = "chat"

        entity = getattr(event, search, None)
        if entity_type == "user" and isinstance(entity, User):
            return entity
        if entity_type == "chat" and isinstance(entity, Chat):
            return entity

        message = getattr(event, "message", None)
        if message is not None:
            found = getattr(message, search, None)
            if entity_type == "user" and isinstance(found, User):
                return found
            if entity_type == "chat" and isinstance(found, Chat):
                return found

        if entity_type == "user" and isinstance(event, ChatMemberUpdated):
            return event.new_chat_member.user

        return None

    @staticmethod
    def _to_user_ctx(user: User) -> UserContext:
        return UserContext(
            tg_id=user.id,
            is_bot=user.is_bot,
            first_name=NonEmptyStr(user.first_name),
            last_name=NonEmptyStr(user.last_name) if user.last_name else None,
            username=user.username,
            language_code=user.language_code,
            has_tg_premium=bool(user.is_premium),
            is_active=True,
        )

    @staticmethod
    def _to_chat_ctx(chat: Chat) -> ChatContext:
        return ChatContext(
            tg_id=chat.id,
            type=ChatType(chat.type),
            title=chat.title,
            username=chat.username,
            is_active=True,
        )
