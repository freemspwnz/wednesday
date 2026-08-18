from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserRole
from domain.user.exceptions import ValidationError
from domain.user.policies import BanAssigned, BanDurationPolicy, NoBan

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
            runner=lambda: self._ban(
                user_id=user_id,
                actor=actor,
                until=until,
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
            runner=lambda: self._unban(
                user_id=user_id,
                actor=actor,
                at=at,
            ),
        )

    async def expire_ban_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        return await self._run_mutating(
            action="expire_ban_if_due",
            user_id=user_id,
            runner=lambda: self._expire_ban_if_due(user_id=user_id, at=at),
        )

    async def assign_ban(self, *, user_id: UserId, at: AwareDatetime) -> User:
        """Record a moderation strike and ban when BanDurationPolicy assigns one."""
        return await self._run_mutating(
            action="assign_ban",
            user_id=user_id,
            runner=lambda: self._assign_ban(user_id=user_id, at=at),
        )

    async def _ban(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        until: AwareDatetime,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        user.ban(actor=actor, until=until, at=at)
        await self._uow.users.save(user)
        return user

    async def _unban(
        self,
        *,
        user_id: UserId,
        actor: UserRole,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        user.unban(actor=actor, at=at)
        await self._uow.users.save(user)
        return user

    async def _expire_ban_if_due(
        self,
        *,
        user_id: UserId,
        at: AwareDatetime,
    ) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        user.expire_ban_if_due(at=at)
        await self._uow.users.save(user)
        return user

    async def _assign_ban(self, *, user_id: UserId, at: AwareDatetime) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        await self._uow.violations.record_violation(user_id, at)
        stats = await self._uow.violations.get_violation_stats(user_id)

        decision = BanDurationPolicy.evaluate(stats=stats, at=at)
        match decision:
            case NoBan():
                return user
            case BanAssigned(banned_until=until):
                user.ban(actor=UserRole.SYSTEM, until=until, at=at)
                await self._uow.users.save(user)
                return user
            case _:
                raise ValidationError("unknown ban duration decision")
