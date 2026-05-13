from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.dto import UserContext
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import BannedState, SubscriptionTier, User, UserId, UserRole

USER_SNAPSHOT_VERSION = 1


class UserSnapshot(BaseModel):
    v: int = USER_SNAPSHOT_VERSION
    id: str
    tg_id: int
    is_bot: bool
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool = False
    role: int
    is_active: bool
    is_banned: bool
    banned_until: datetime | None = None
    subscription_tier: int
    subscription_daily_limit: int
    subscription_cooldown_minutes: int
    subscription_started_at: datetime
    subscription_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> "UserSnapshot":
        is_banned = isinstance(user.state, BannedState)
        banned_until = user.state.until.value if isinstance(user.state, BannedState) else None
        return cls(
            id=str(user.id.value),
            tg_id=user.profile.telegram_id,
            is_bot=user.profile.is_bot,
            first_name=str(user.profile.first_name),
            last_name=str(user.profile.last_name) if user.profile.last_name is not None else None,
            username=user.profile.username,
            language_code=user.profile.language_code,
            has_tg_premium=user.profile.has_tg_premium,
            role=int(user.role),
            is_active=not is_banned,
            is_banned=is_banned,
            banned_until=banned_until,
            subscription_tier=int(user.subscription.plan.tier),
            subscription_daily_limit=user.subscription.plan.daily_limit,
            subscription_cooldown_minutes=user.subscription.plan.cooldown_minutes,
            subscription_started_at=user.subscription.started_at.value,
            subscription_expires_at=(
                user.subscription.expires_at.value if user.subscription.expires_at is not None else None
            ),
            created_at=user.created_at.value,
            updated_at=user.updated_at.value,
            last_seen_at=user.last_seen_at.value,
        )

    def to_context(self) -> UserContext:
        banned_until = AwareDatetime(self.banned_until) if self.banned_until is not None else None
        return UserContext(
            id=UserId(UUID(self.id)),
            tg_id=self.tg_id,
            is_bot=self.is_bot,
            first_name=NonEmptyStr(self.first_name),
            last_name=NonEmptyStr(self.last_name) if self.last_name else None,
            username=self.username,
            language_code=self.language_code,
            has_tg_premium=self.has_tg_premium,
            role=UserRole(self.role),
            is_active=self.is_active,
            is_banned=self.is_banned,
            banned_until=banned_until,
            subscription_tier=SubscriptionTier(self.subscription_tier),
            subscription_daily_limit=self.subscription_daily_limit,
            subscription_cooldown_minutes=self.subscription_cooldown_minutes,
            subscription_started_at=AwareDatetime(self.subscription_started_at),
            subscription_expires_at=(
                AwareDatetime(self.subscription_expires_at) if self.subscription_expires_at else None
            ),
            created_at=AwareDatetime(self.created_at),
            updated_at=AwareDatetime(self.updated_at),
            last_seen_at=AwareDatetime(self.last_seen_at),
        )
