"""Shared context / JSON builders for Redis persistence unit tests."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.dto import ChatContext, UserContext
from domain.catalog import SubscriptionTier
from domain.user.vo.roles import UserRole
from infra.persistence.redis.codec import (
    CHAT_CONTEXT_VERSION,
    USER_CONTEXT_VERSION,
    dump_chat_context,
    dump_user_context,
)


def _now() -> datetime:
    return datetime(2025, 5, 1, 12, 0, 0, tzinfo=UTC)


def mk_user_context(**kwargs: object) -> UserContext:
    now = _now()
    data: dict[str, object] = {
        "id": str(uuid4()),
        "tg_id": 1001,
        "is_bot": False,
        "first_name": "Ada",
        "role": int(UserRole.USER),
        "is_active": True,
        "is_banned": False,
        "is_admin": False,
        "subscription_tier": int(SubscriptionTier.FREE),
        "subscription_daily_limit": 3,
        "subscription_cooldown_minutes": 0,
        "subscription_started_at": now,
        "model_vendor": "sber",
        "model_series": "gigachat",
        "model": "gigachat-2-lite",
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
    }
    data.update(kwargs)
    return UserContext(**data)  # type: ignore[arg-type]


def mk_chat_context(**kwargs: object) -> ChatContext:
    now = _now()
    data: dict[str, object] = {
        "id": str(uuid4()),
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
    return ChatContext(**data)  # type: ignore[arg-type]


def user_payload(**kwargs: object) -> str:
    """JSON wire payload; pass ``v=...`` to override version after dump."""
    version = kwargs.pop("v", None)
    payload = dump_user_context(mk_user_context(**kwargs))
    if version is None:
        return payload
    data = json.loads(payload)
    data["v"] = version
    return json.dumps(data)


def chat_payload(**kwargs: object) -> str:
    version = kwargs.pop("v", None)
    payload = dump_chat_context(mk_chat_context(**kwargs))
    if version is None:
        return payload
    data = json.loads(payload)
    data["v"] = version
    return json.dumps(data)


__all__ = [
    "CHAT_CONTEXT_VERSION",
    "USER_CONTEXT_VERSION",
    "chat_payload",
    "mk_chat_context",
    "mk_user_context",
    "user_payload",
]
