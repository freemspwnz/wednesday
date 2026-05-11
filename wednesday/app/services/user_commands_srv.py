from __future__ import annotations

from app.exceptions import UserNotFoundError
from app.protocols import ILogger
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserProfile, UserRepo, UserRole, UserSubscription


class UserCommandService:
    """Загрузка агрегата, доменная команда и сохранение (без транзакции — её закрывает UoW)."""

    def __init__(self, *, logger: ILogger) -> None:
        self._logger = logger.bind(module=self.__class__.__name__)

    @staticmethod
    async def _load_user_or_raise(repo: UserRepo, user_id: UserId) -> User:
        entity = await repo.get_by_id(user_id)
        if entity is None:
            raise UserNotFoundError(user_id)
        return entity

    async def change_role(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        actor: UserRole,
        new_role: UserRole,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.change_role(actor=actor, new_role=new_role, at=at)
        await repo.save(user)
        self._logger.info(
            "User aggregate updated",
            action="change_role",
            user_id=str(user.id),
            new_role=str(new_role),
        )
        return user

    async def change_profile(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        actor: UserRole,
        new_profile: UserProfile,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.change_profile(actor=actor, new_profile=new_profile, at=at)
        await repo.save(user)
        self._logger.info(
            "User aggregate updated",
            action="change_profile",
            user_id=str(user.id),
        )
        return user

    async def change_subscription(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        actor: UserRole,
        new_subscription: UserSubscription,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.change_subscription(actor=actor, new_subscription=new_subscription, at=at)
        await repo.save(user)
        self._logger.info(
            "User aggregate updated",
            action="change_subscription",
            user_id=str(user.id),
        )
        return user

    async def ban(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        actor: UserRole,
        until: AwareDatetime,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.ban(actor=actor, until=until, at=at)
        await repo.save(user)
        self._logger.info(
            "User aggregate updated",
            action="ban",
            user_id=str(user.id),
        )
        return user

    async def unban(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        actor: UserRole,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.unban(actor=actor, at=at)
        await repo.save(user)
        self._logger.info(
            "User aggregate updated",
            action="unban",
            user_id=str(user.id),
        )
        return user

    async def expire_ban_if_due(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.expire_ban_if_due(at=at)
        await repo.save(user)
        self._logger.debug(
            "User aggregate persisted",
            action="expire_ban_if_due",
            user_id=str(user.id),
        )
        return user

    async def expire_subscription_if_due(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.expire_subscription_if_due(at=at)
        await repo.save(user)
        self._logger.debug(
            "User aggregate persisted",
            action="expire_subscription_if_due",
            user_id=str(user.id),
        )
        return user

    async def mark_seen(
        self,
        *,
        repo: UserRepo,
        user_id: UserId,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(repo, user_id)
        user.mark_seen_at(at=at)
        await repo.save(user)
        self._logger.debug(
            "User aggregate persisted",
            action="mark_seen",
            user_id=str(user.id),
        )
        return user
