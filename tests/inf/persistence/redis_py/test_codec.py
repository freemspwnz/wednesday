"""Redis context codec tests (JSON ↔ DTO)."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.dto import UserContext
from app.exceptions import CacheInvalidDataError, CacheStaleDataError
from domain.catalog import Model, Series, Vendor
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.vo import UserSettings, UserSubscription
from infra.persistence.redis.codec import (
    dump_chat_context,
    dump_user_context,
    load_chat_context,
    load_user_context,
)
from tests.dom.catalog.plans import FREE_PLAN

from .contexts import chat_payload, mk_chat_context, mk_user_context, user_payload


@pytest.mark.unit
class TestUserContextCodec:
    def test_json_roundtrip(self) -> None:
        ctx = mk_user_context(tg_id=1001)
        restored = load_user_context(dump_user_context(ctx))
        assert restored.tg_id == ctx.tg_id
        assert restored.id == ctx.id
        assert restored.model_vendor == "sber"
        assert restored.model_series == "gigachat"
        assert restored.model == "gigachat-2-lite"
        assert restored.is_admin is False
        assert restored.created_at == ctx.created_at

    def test_from_domain_roundtrip_preserves_settings(self) -> None:
        now = AwareDatetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
        user = User.register(
            id=UserId(UUID(int=42)),
            profile=UserProfile(telegram_id=1001, is_bot=False, first_name=NonEmptyStr("Ada")),
            role=UserRole.USER,
            subscription=UserSubscription(plan=FREE_PLAN, started_at=now, expires_at=None),
            settings=UserSettings(
                vendor=Vendor.parse("sber"),
                series=Series.parse("gigachat"),
                model=Model.parse("gigachat-2-lite"),
            ),
            at=now,
        )

        ctx = UserContext.from_domain(user)
        restored = load_user_context(dump_user_context(ctx))
        assert restored.model_vendor == "sber"
        assert restored.model_series == "gigachat"
        assert restored.model == "gigachat-2-lite"
        assert restored.id == str(user.id)
        assert restored.banned_until is None

    def test_stale_version_raises(self) -> None:
        with pytest.raises(CacheStaleDataError):
            load_user_context(user_payload(v=1))

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(CacheInvalidDataError):
            load_user_context("{")

    def test_missing_version_raises_invalid(self) -> None:
        with pytest.raises(CacheInvalidDataError):
            load_user_context("{}")


@pytest.mark.unit
class TestChatContextCodec:
    def test_json_roundtrip(self) -> None:
        ctx = mk_chat_context()
        restored = load_chat_context(dump_chat_context(ctx))
        assert restored.tg_id == ctx.tg_id
        assert restored.id == ctx.id
        assert restored.schedules == [(10, 30)]
        assert restored.timezone == "Etc/UTC"

    def test_stale_version_raises(self) -> None:
        with pytest.raises(CacheStaleDataError):
            load_chat_context(chat_payload(v=999))
