from dataclasses import dataclass

from domain.catalog import SubscriptionTier
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import BannedState, User, UserId, UserRole


@dataclass
class UserContext:
    """Registered user read-model for handlers and cache (always fully materialized)."""

    id: UserId
    tg_id: int
    is_bot: bool
    first_name: NonEmptyStr
    role: UserRole
    is_active: bool
    is_banned: bool
    subscription_tier: SubscriptionTier
    subscription_daily_limit: int
    subscription_cooldown_minutes: int
    subscription_started_at: AwareDatetime
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_seen_at: AwareDatetime
    model_vendor: str
    model_series: str
    model: str
    last_name: NonEmptyStr | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool = False
    banned_until: AwareDatetime | None = None
    subscription_expires_at: AwareDatetime | None = None

    @classmethod
    def from_domain(cls, user: User) -> "UserContext":
        is_banned = isinstance(user.state, BannedState)
        banned_until = user.state.until if isinstance(user.state, BannedState) else None
        return UserContext(
            id=user.id,
            tg_id=user.profile.telegram_id,
            is_bot=user.profile.is_bot,
            first_name=user.profile.first_name,
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
            model_vendor=str(user.settings.vendor),
            model_series=str(user.settings.series),
            model=str(user.settings.model),
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_seen_at=user.last_seen_at,
        )
