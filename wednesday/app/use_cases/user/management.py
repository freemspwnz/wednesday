from domain.kernel.vo import AwareDatetime
from domain.user import (
    User,
    UserId,
    UserManagementService,
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
            runner=lambda: UserManagementService.change_role(
                id=user_id,
                actor=actor,
                new_role=new_role,
                repo=self._uow.users,
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
            runner=lambda: UserManagementService.change_profile(
                id=user_id,
                actor=actor,
                new_profile=new_profile,
                repo=self._uow.users,
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
            runner=lambda: UserManagementService.change_subscription(
                id=user_id,
                actor=actor,
                new_subscription=new_subscription,
                repo=self._uow.users,
                at=at,
            ),
        )
