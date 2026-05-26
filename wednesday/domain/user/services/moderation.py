from ..exceptions import ValidationError
from ..policies import (
    BanAssigned,
    BanDurationPolicy,
    NoBan,
)
from ..protocols import ViolationRepo
from ..user import User
from ..vo import AwareDatetime, UserRole


class UserModerationService:
    @staticmethod
    async def assign_ban(
        user: User,
        repo: ViolationRepo,
        at: AwareDatetime,
    ) -> None:
        user = User.ensure(user)
        repo = ViolationRepo.ensure(repo)
        at = AwareDatetime.ensure(at)

        stats = await repo.get_violation_stats(user.id)

        decision = BanDurationPolicy.evaluate(
            stats=stats,
            at=at,
        )

        match decision:
            case NoBan():
                return
            case BanAssigned(banned_until=until):
                user.ban(actor=UserRole.SYSTEM, until=until, at=at)
            case _:
                raise ValidationError("unknown ban duration decision")
