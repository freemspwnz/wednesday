from collections.abc import Awaitable, Callable

from app.dto import ChatContext
from app.protocols import CacheRepo, Logger, UoW
from domain.chat import Chat, ChatId


class ChatBaseUseCase:
    """Shared UoW + cache orchestration for chat command use cases."""

    _uow: UoW
    _cache: CacheRepo[ChatContext, Chat]
    _logger: Logger

    def __init__(
        self,
        *,
        uow: UoW,
        cache: CacheRepo[ChatContext, Chat],
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._cache = cache
        self._logger = logger.bind(module=self.__class__.__name__)

    def _log_scenario_start(self, *, action: str, chat_id: ChatId) -> None:
        self._logger.debug(
            "Chat command scenario started",
            action=action,
            chat_id=str(chat_id.value),
        )

    async def _run_mutating(
        self,
        *,
        action: str,
        chat_id: ChatId,
        runner: Callable[[], Awaitable[Chat]],
    ) -> Chat:
        self._log_scenario_start(action=action, chat_id=chat_id)
        async with self._uow:
            chat = await runner()
        await self._cache.set(chat)
        self._logger.debug(
            "Chat cache snapshot refreshed",
            action=action,
            tg_id=chat.profile.telegram_id,
        )
        return chat
