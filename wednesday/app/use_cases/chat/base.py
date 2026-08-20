from collections.abc import Awaitable, Callable
from uuid import UUID

from app.dto import ChatContext
from app.protocols import CacheRepo, Logger, UoW
from domain.chat import Chat, ChatId, ChatMember, ChatMemberId, ChatMemberRole, ChatNotFoundError


class ChatBaseUseCase:
    """Shared UoW + cache orchestration for chat command use cases."""

    _uow: UoW
    _cache: CacheRepo[ChatContext]
    _logger: Logger

    def __init__(
        self,
        *,
        uow: UoW,
        cache: CacheRepo[ChatContext],
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._cache = cache
        self._logger = logger.bind(module=self.__class__.__name__)

    def _log_scenario_start(self, *, action: str, chat_id: str) -> None:
        self._logger.debug(
            "Chat command scenario started",
            action=action,
            chat_id=chat_id,
        )

    async def _run_mutating(
        self,
        *,
        action: str,
        chat_id: str,
        runner: Callable[[], Awaitable[Chat]],
    ) -> ChatContext:
        self._log_scenario_start(action=action, chat_id=chat_id)
        async with self._uow:
            chat = await runner()
        ctx = ChatContext.from_domain(chat)
        await self._cache.set(ctx)
        self._logger.debug(
            "Chat cache snapshot refreshed",
            action=action,
            tg_id=ctx.tg_id,
        )
        return ctx

    async def _load_chat_or_raise(self, *, chat_id: ChatId) -> Chat:
        chat = await self._uow.chats.get_by_id(chat_id)
        if chat is None:
            raise ChatNotFoundError(str(chat_id))
        return chat

    @staticmethod
    def _actor(actor_id: int, actor_role: str, chat_id: str) -> ChatMember:
        return ChatMember(
            id=ChatMemberId(actor_id),
            role=ChatMemberRole(actor_role),
            chat_id=ChatId(UUID(chat_id)),
        )
