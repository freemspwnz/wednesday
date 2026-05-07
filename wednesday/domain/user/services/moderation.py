from ..exceptions import ValidationError
from ..policies import (
    BanAssigned,
    BanDurationPolicy,
    NoBan,
    ViolationStats,
)
from ..user import User
from ..vo import AwareDatetime, UserRole


class UserModerationService:
    @staticmethod
    def assign_ban(
        user: User,
        stats: ViolationStats,
        at: AwareDatetime,
    ) -> None:
        user = User.ensure(user)
        if not isinstance(stats, ViolationStats):
            raise ValidationError("stats must be a ViolationStats")
        at = AwareDatetime.ensure(at)

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
