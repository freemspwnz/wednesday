from __future__ import annotations

from ..exceptions import UserNotFoundError, ValidationError
from ..policies import (
    BanAssigned,
    BanDurationPolicy,
    NoBan,
)
from ..protocols import UserRepo, ViolationRepo
from ..user import User
from ..vo import AwareDatetime, UserId, UserRole


class UserModerationService:
    @staticmethod
    async def assign_ban(
        *,
        user_id: UserId,
        user_repo: UserRepo,
        violation_repo: ViolationRepo,
        at: AwareDatetime,
    ) -> User:
        user_id = UserId.ensure(user_id)
        at = AwareDatetime.ensure(at)
        if not isinstance(user_repo, UserRepo):
            raise ValidationError("user_repo must implement UserRepo")
        if not isinstance(violation_repo, ViolationRepo):
            raise ValidationError("violation_repo must implement ViolationRepo")

        user = await user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))

        stats = await violation_repo.get_violation_stats(user_id)

        decision = BanDurationPolicy.evaluate(
            stats=stats,
            at=at,
        )

        match decision:
            case NoBan():
                return user
            case BanAssigned(banned_until=until):
                await violation_repo.record_violation(user_id, at)
                user.ban(actor=UserRole.SYSTEM, until=until, at=at)
                await user_repo.save(user)
                return user
            case _:
                raise ValidationError("unknown ban duration decision")
