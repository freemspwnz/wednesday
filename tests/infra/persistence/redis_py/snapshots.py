"""Общие билдеры снимков для unit-тестов Redis persistence (не собираются pytest как тесты)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from domain.user.vo.roles import UserRole
from domain.user.vo.subscription.tier import SubscriptionTier
from infra.persistence.redis.snapshots.chat import CHAT_SNAPSHOT_VERSION, ChatSnapshot
from infra.persistence.redis.snapshots.user import USER_SNAPSHOT_VERSION, UserSnapshot


def user_snapshot(**kwargs: object) -> UserSnapshot:
    now = datetime(2025, 5, 1, 12, 0, 0, tzinfo=UTC)
    data: dict[str, object] = {
        "v": USER_SNAPSHOT_VERSION,
        "id": str(uuid4()),
        "tg_id": 1001,
        "is_bot": False,
        "first_name": "Ada",
        "role": int(UserRole.USER),
        "is_active": True,
        "is_banned": False,
        "subscription_tier": int(SubscriptionTier.FREE),
        "subscription_daily_limit": 3,
        "subscription_cooldown_minutes": 0,
        "subscription_started_at": now,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }
    data.update(kwargs)
    return UserSnapshot.model_validate(data)


def chat_snapshot(**kwargs: object) -> ChatSnapshot:
    now = datetime(2025, 5, 1, 12, 0, 0, tzinfo=UTC)
    cid = str(uuid4())
    data: dict[str, object] = {
        "v": CHAT_SNAPSHOT_VERSION,
        "id": cid,
        "tg_id": 2002,
        "type": "group",
        "is_active": True,
        "timezone": "Etc/UTC",
        "weekday": 3,
        "schedules": [(10, 30)],
        "created_at": now,
        "updated_at": now,
    }
    data.update(kwargs)
    return ChatSnapshot.model_validate(data)
