from domain.kernel.vo import AwareDatetime
from domain.user import (
    User,
    UserId,
    UserProfile,
    UserRole,
    UserSubscription,
)

from .base import UserBaseUseCase


class UserManagementUseCase(UserBaseUseCase):
    """User management use case methods."""

    async def change_role(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_role: UserRole,
        at: AwareDatetime,
    ) -> User:
        return await self._run_mutating(
            action="change_role",
            user_id=user_id,
            runner=lambda: self._change_role(
                user_id=user_id,
                actor=actor,
                new_role=new_role,
                at=at,
            ),
        )

    async def change_profile(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_profile: UserProfile,
        at: AwareDatetime,
    ) -> User:
        return await self._run_mutating(
            action="change_profile",
            user_id=user_id,
            runner=lambda: self._change_profile(
                user_id=user_id,
                actor=actor,
                new_profile=new_profile,
                at=at,
            ),
        )

    async def change_subscription(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_subscription: UserSubscription,
        at: AwareDatetime,
    ) -> User:
        return await self._run_mutating(
            action="change_subscription",
            user_id=user_id,
            runner=lambda: self._change_subscription(
                user_id=user_id,
                actor=actor,
                new_subscription=new_subscription,
                at=at,
            ),
        )

    async def _change_role(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_role: UserRole,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        user.change_role(actor=actor, new_role=new_role, at=at)
        await self._uow.users.save(user)
        return user

    async def _change_profile(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_profile: UserProfile,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        user.change_profile(actor=actor, new_profile=new_profile, at=at)
        await self._uow.users.save(user)
        return user

    async def _change_subscription(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        new_subscription: UserSubscription,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        user.change_subscription(actor=actor, new_subscription=new_subscription, at=at)
        await self._uow.users.save(user)
        return user
