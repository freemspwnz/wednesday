from collections.abc import Awaitable, Callable

from app.dto import UserContext
from app.protocols import CacheRepo, Logger, UoW
from domain.user import User, UserId, UserNotFoundError


class UserBaseUseCase:
    """Shared UoW + cache orchestration for user command use cases."""

    _uow: UoW
    _cache: CacheRepo[UserContext]
    _logger: Logger

    def __init__(
        self,
        *,
        uow: UoW,
        cache: CacheRepo[UserContext],
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._cache = cache
        self._logger = logger.bind(module=self.__class__.__name__)

    def _log_scenario_start(self, *, action: str, user_id: str) -> None:
        self._logger.debug(
            "User command scenario started",
            action=action,
            user_id=user_id,
        )

    async def _run_mutating(
        self,
        *,
        action: str,
        user_id: str,
        runner: Callable[[], Awaitable[User]],
    ) -> UserContext:
        self._log_scenario_start(action=action, user_id=user_id)
        async with self._uow:
            user = await runner()
        ctx = UserContext.from_domain(user)
        await self._cache.set(ctx)
        self._logger.debug(
            "User cache snapshot refreshed",
            action=action,
            tg_id=ctx.tg_id,
        )
        return ctx

    async def _load_user_or_raise(self, *, user_id: UserId) -> User:
        user = await self._uow.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))
        return user
