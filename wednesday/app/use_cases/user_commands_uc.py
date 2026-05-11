from __future__ import annotations

from app.protocols import ILogger, IUoW
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserProfile, UserRole, UserSubscription

from ..services import UserCommandService


class UserCommandsUseCase:
    """Фасад доменных команд user-агрегата в рамках одной транзакции UoW."""

    def __init__(
        self,
        *,
        uow: IUoW,
        user_commands: UserCommandService,
        logger: ILogger,
    ) -> None:
        self._uow = uow
        self._user_commands = user_commands
        self._logger = logger.bind(module=self.__class__.__name__)

    def _log_scenario_start(self, *, action: str, user_id: UserId) -> None:
        self._logger.debug(
            "User command scenario started",
            action=action,
            user_id=str(user_id),
        )

    async def change_role(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_role: UserRole,
        at: AwareDatetime,
    ) -> User:
        self._log_scenario_start(action="change_role", user_id=user_id)
        async with self._uow:
            return await self._user_commands.change_role(
                repo=self._uow.users,
                user_id=user_id,
                actor=actor,
                new_role=new_role,
                at=at,
            )

    async def change_profile(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_profile: UserProfile,
        at: AwareDatetime,
    ) -> User:
        self._log_scenario_start(action="change_profile", user_id=user_id)
        async with self._uow:
            return await self._user_commands.change_profile(
                repo=self._uow.users,
                user_id=user_id,
                actor=actor,
                new_profile=new_profile,
                at=at,
            )

    async def change_subscription(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_subscription: UserSubscription,
        at: AwareDatetime,
    ) -> User:
        self._log_scenario_start(action="change_subscription", user_id=user_id)
        async with self._uow:
            return await self._user_commands.change_subscription(
                repo=self._uow.users,
                user_id=user_id,
                actor=actor,
                new_subscription=new_subscription,
                at=at,
            )

    async def ban(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        until: AwareDatetime,
        at: AwareDatetime,
    ) -> User:
        self._log_scenario_start(action="ban", user_id=user_id)
        async with self._uow:
            return await self._user_commands.ban(
                repo=self._uow.users,
                user_id=user_id,
                actor=actor,
                until=until,
                at=at,
            )

    async def unban(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        at: AwareDatetime,
    ) -> User:
        self._log_scenario_start(action="unban", user_id=user_id)
        async with self._uow:
            return await self._user_commands.unban(
                repo=self._uow.users,
                user_id=user_id,
                actor=actor,
                at=at,
            )

    async def expire_ban_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        self._log_scenario_start(action="expire_ban_if_due", user_id=user_id)
        async with self._uow:
            return await self._user_commands.expire_ban_if_due(
                repo=self._uow.users,
                user_id=user_id,
                at=at,
            )

    async def expire_subscription_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        self._log_scenario_start(action="expire_subscription_if_due", user_id=user_id)
        async with self._uow:
            return await self._user_commands.expire_subscription_if_due(
                repo=self._uow.users,
                user_id=user_id,
                at=at,
            )

    async def mark_seen(self, *, user_id: UserId, at: AwareDatetime) -> User:
        self._log_scenario_start(action="mark_seen", user_id=user_id)
        async with self._uow:
            return await self._user_commands.mark_seen(
                repo=self._uow.users,
                user_id=user_id,
                at=at,
            )
