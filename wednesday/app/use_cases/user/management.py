from datetime import datetime
from typing import Literal
from uuid import UUID

from app.dto import UserContext
from domain.kernel.vo import AwareDatetime
from domain.user import (
    User,
    UserId,
    UserRole,
)

from .base import UserBaseUseCase


class UserManagementUseCase(UserBaseUseCase):
    """User management use case methods."""

    async def change_role(
        self,
        *,
        user_id: str,
        actor: int,
        action: Literal["promote", "demote"],
        at: datetime,
    ) -> UserContext:
        return await self._run_mutating(
            action="change_role",
            user_id=user_id,
            runner=lambda: self._change_role(
                user_id=UserId(UUID(user_id)),
                actor=UserRole(actor),
                action=action,
                at=AwareDatetime.from_datetime(at),
            ),
        )

    async def _change_role(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        action: Literal["promote", "demote"],
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        new_role = UserRole(user.role + 1) if action == "promote" else UserRole(user.role - 1)
        user.change_role(actor=actor, new_role=new_role, at=at)
        await self._uow.users.save(user)
        return user
