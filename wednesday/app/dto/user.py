from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Self

from domain.user import BannedState, User, UserRole


@dataclass
class UserContext:
    """Registered user read-model for handlers and cache (always fully materialized)."""

    _ROLE_LABELS: ClassVar[dict[int, str]] = {
        0: "Пользователь",  # UserRole.USER
        1: "Администратор",
        2: "Владелец",
        3: "Система",
    }

    _TIER_LABELS: ClassVar[dict[int, str]] = {
        0: "Бесплатная",
        1: "Премиум",
    }

    id: str
    tg_id: int
    is_bot: bool
    first_name: str
    role: int
    is_active: bool
    is_banned: bool
    is_admin: bool
    model: str
    model_series: str
    model_vendor: str
    subscription_tier: int
    subscription_daily_limit: int
    subscription_cooldown_minutes: int
    subscription_started_at: datetime
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool | None = None
    banned_until: datetime | None = None
    subscription_expires_at: datetime | None = None

    @classmethod
    def from_domain(cls, user: User) -> Self:
        is_banned = isinstance(user.state, BannedState)
        banned_until = user.state.until if isinstance(user.state, BannedState) else None
        return cls(
            id=str(user.id),
            tg_id=user.profile.telegram_id,
            is_bot=user.profile.is_bot,
            first_name=str(user.profile.first_name),
            last_name=str(user.profile.last_name) if user.profile.last_name is not None else None,
            username=user.profile.username,
            language_code=user.profile.language_code,
            has_tg_premium=user.profile.has_tg_premium,
            role=int(user.role),
            is_admin=user.role in {UserRole.ADMIN, UserRole.OWNER},
            is_active=not is_banned,
            is_banned=is_banned,
            banned_until=banned_until.value if banned_until is not None else None,
            subscription_tier=int(user.subscription.plan.tier),
            subscription_daily_limit=user.subscription.plan.daily_limit,
            subscription_cooldown_minutes=user.subscription.plan.cooldown_minutes,
            subscription_started_at=user.subscription.started_at.value,
            subscription_expires_at=(
                user.subscription.expires_at.value if user.subscription.expires_at is not None else None
            ),
            model_vendor=str(user.settings.vendor),
            model_series=str(user.settings.series),
            model=str(user.settings.model),
            created_at=user.created_at.value,
            updated_at=user.updated_at.value,
            last_seen_at=user.last_seen_at.value,
        )

    @property
    def role_label(self) -> str:
        return self._ROLE_LABELS[self.role]

    @property
    def subscription_label(self) -> str:
        return self._TIER_LABELS[self.subscription_tier]
