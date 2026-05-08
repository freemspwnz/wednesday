from dataclasses import dataclass

from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import BannedState, SubscriptionTier, User, UserId, UserRole


@dataclass
class UserContext:
    tg_id: int
    is_bot: bool
    first_name: NonEmptyStr
    id: UserId | None = None
    last_name: NonEmptyStr | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool = False
    role: UserRole | None = None
    is_active: bool = True
    is_banned: bool = False
    banned_until: AwareDatetime | None = None
    subscription_tier: SubscriptionTier | None = None
    subscription_daily_limit: int | None = None
    subscription_cooldown_minutes: int | None = None
    subscription_started_at: AwareDatetime | None = None
    subscription_expires_at: AwareDatetime | None = None
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    last_seen_at: AwareDatetime | None = None

    @classmethod
    def from_domain(cls, user: User) -> "UserContext":
        is_banned = isinstance(user.state, BannedState)
        banned_until = user.state.until if isinstance(user.state, BannedState) else None
        return UserContext(
            tg_id=user.profile.telegram_id,
            is_bot=user.profile.is_bot,
            first_name=user.profile.first_name,
            id=user.id,
            last_name=user.profile.last_name,
            username=user.profile.username,
            language_code=user.profile.language_code,
            has_tg_premium=user.profile.has_tg_premium,
            role=user.role,
            is_active=not is_banned,
            is_banned=is_banned,
            banned_until=banned_until,
            subscription_tier=user.subscription.plan.tier,
            subscription_daily_limit=user.subscription.plan.daily_limit,
            subscription_cooldown_minutes=user.subscription.plan.cooldown_minutes,
            subscription_started_at=user.subscription.started_at,
            subscription_expires_at=user.subscription.expires_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_seen_at=user.last_seen_at,
        )
