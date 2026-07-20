from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserModerationService, UserRole

from .base import UserBaseUseCase


class UserModerationUseCase(UserBaseUseCase):
    """User moderation use case methods (ban/unban)."""

    async def ban(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        until: AwareDatetime,
        at: AwareDatetime,
    ) -> User:
        return await self._run_mutating(
            action="ban",
            user_id=user_id,
            runner=lambda: UserModerationService.ban(
                id=user_id,
                actor=actor,
                until=until,
                repo=self._uow.users,
                at=at,
            ),
        )

    async def unban(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        at: AwareDatetime,
    ) -> User:
        return await self._run_mutating(
            action="unban",
            user_id=user_id,
            runner=lambda: UserModerationService.unban(
                id=user_id,
                actor=actor,
                repo=self._uow.users,
                at=at,
            ),
        )

    async def expire_ban_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        return await self._run_mutating(
            action="expire_ban_if_due",
            user_id=user_id,
            runner=lambda: UserModerationService.expire_ban_if_due(
                id=user_id,
                repo=self._uow.users,
                at=at,
            ),
        )
