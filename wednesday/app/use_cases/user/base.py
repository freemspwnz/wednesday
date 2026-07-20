from collections.abc import Awaitable, Callable

from app.dto import UserContext
from app.protocols import CacheRepo, Logger, UoW
from domain.user import User, UserId


class UserBaseUseCase:
    """Shared UoW + cache orchestration for user command use cases."""

    _uow: UoW
    _cache: CacheRepo[UserContext, User]
    _logger: Logger

    def __init__(
        self,
        *,
        uow: UoW,
        cache: CacheRepo[UserContext, User],
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._cache = cache
        self._logger = logger.bind(module=self.__class__.__name__)

    def _log_scenario_start(self, *, action: str, user_id: UserId) -> None:
        self._logger.debug(
            "User command scenario started",
            action=action,
            user_id=str(user_id),
        )

    async def _run_mutating(
        self,
        *,
        action: str,
        user_id: UserId,
        runner: Callable[[], Awaitable[User]],
    ) -> User:
        self._log_scenario_start(action=action, user_id=user_id)
        async with self._uow:
            user = await runner()
        await self._cache.set(user)
        self._logger.debug(
            "User cache snapshot refreshed",
            action=action,
            tg_id=user.profile.telegram_id,
        )
        return user
