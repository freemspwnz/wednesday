from datetime import UTC, datetime

from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserProfile, UserRole, UserTelegramId
from domain.user.vo import UserSubscription


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def mk_user(
    *,
    user_id: int = 1,
    role: UserRole = UserRole.USER,
    now: AwareDatetime | None = None,
) -> User:
    current = now or dt(12)
    return User.create(
        id=UserTelegramId(user_id),
        profile=UserProfile(is_bot=False, first_name=NonEmptyStr("Test")),
        role=role,
        subscription=UserSubscription.free(current),
        now=current,
    )
