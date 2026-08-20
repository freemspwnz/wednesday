from datetime import datetime
from typing import Self

from pydantic import BaseModel

from app.dto import UserContext

USER_SNAPSHOT_VERSION = 3


class UserSnapshot(BaseModel):
    v: int = USER_SNAPSHOT_VERSION
    id: str
    tg_id: int
    is_bot: bool
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool | None = None
    role: int
    is_active: bool
    is_banned: bool
    is_admin: bool
    banned_until: datetime | None = None
    subscription_tier: int
    subscription_daily_limit: int
    subscription_cooldown_minutes: int
    subscription_started_at: datetime
    subscription_expires_at: datetime | None = None
    model_vendor: str
    model_series: str
    model: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_context(cls, context: UserContext) -> Self:
        return cls(
            id=context.id,
            tg_id=context.tg_id,
            is_bot=context.is_bot,
            first_name=context.first_name,
            last_name=context.last_name,
            username=context.username,
            language_code=context.language_code,
            has_tg_premium=context.has_tg_premium,
            role=context.role,
            is_active=context.is_active,
            is_banned=context.is_banned,
            is_admin=context.is_admin,
            banned_until=context.banned_until,
            subscription_tier=context.subscription_tier,
            subscription_daily_limit=context.subscription_daily_limit,
            subscription_cooldown_minutes=context.subscription_cooldown_minutes,
            subscription_started_at=context.subscription_started_at,
            subscription_expires_at=context.subscription_expires_at,
            model_vendor=context.model_vendor,
            model_series=context.model_series,
            model=context.model,
            created_at=context.created_at,
            updated_at=context.updated_at,
            last_seen_at=context.last_seen_at,
        )

    def to_context(self) -> UserContext:
        banned_until = self.banned_until if self.banned_until is not None else None
        return UserContext(
            id=self.id,
            tg_id=self.tg_id,
            is_bot=self.is_bot,
            first_name=self.first_name,
            last_name=self.last_name if self.last_name else None,
            username=self.username,
            language_code=self.language_code,
            has_tg_premium=self.has_tg_premium,
            role=self.role,
            is_active=self.is_active,
            is_banned=self.is_banned,
            is_admin=self.is_admin,
            banned_until=banned_until,
            subscription_tier=self.subscription_tier,
            subscription_daily_limit=self.subscription_daily_limit,
            subscription_cooldown_minutes=self.subscription_cooldown_minutes,
            subscription_started_at=self.subscription_started_at,
            subscription_expires_at=(self.subscription_expires_at if self.subscription_expires_at else None),
            model_vendor=self.model_vendor,
            model_series=self.model_series,
            model=self.model,
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_seen_at=self.last_seen_at,
        )
