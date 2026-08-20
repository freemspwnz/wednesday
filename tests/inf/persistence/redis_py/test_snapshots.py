"""Redis Pydantic snapshot tests (JSON ↔ DTO)."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.dto import UserContext
from domain.catalog import Model, Series, Vendor
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.vo import UserSettings, UserSubscription
from infra.persistence.redis.snapshots.chat import ChatSnapshot
from infra.persistence.redis.snapshots.user import USER_SNAPSHOT_VERSION, UserSnapshot
from tests.dom.catalog.plans import FREE_PLAN

from .snapshots import chat_snapshot, user_snapshot


@pytest.mark.unit
class TestUserSnapshot:
    def test_json_roundtrip_and_to_context(self) -> None:
        snap = user_snapshot()
        restored = UserSnapshot.model_validate_json(snap.model_dump_json())
        assert restored.tg_id == snap.tg_id
        ctx = restored.to_context()
        assert ctx.tg_id == snap.tg_id
        assert ctx.id == snap.id
        assert ctx.model_vendor == "sber"
        assert ctx.model_series == "gigachat"
        assert ctx.model == "gigachat-2-lite"
        assert ctx.is_admin is False

    def test_from_context_roundtrip_preserves_settings(self) -> None:
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

        snap = UserSnapshot.from_context(UserContext.from_domain(user))
        assert snap.v == USER_SNAPSHOT_VERSION
        assert snap.model_vendor == "sber"
        assert snap.model_series == "gigachat"
        assert snap.model == "gigachat-2-lite"

        restored = UserSnapshot.model_validate_json(snap.model_dump_json())
        ctx = restored.to_context()
        assert ctx.model_vendor == "sber"
        assert ctx.model_series == "gigachat"
        assert ctx.model == "gigachat-2-lite"
        assert ctx.id == str(user.id)


@pytest.mark.unit
class TestChatSnapshot:
    def test_json_roundtrip_and_to_context(self) -> None:
        snap = chat_snapshot()
        restored = ChatSnapshot.model_validate_json(snap.model_dump_json())
        assert restored.tg_id == snap.tg_id
        ctx = restored.to_context()
        assert ctx.tg_id == snap.tg_id
        assert ctx.id == snap.id
        assert ctx.schedules == [(10, 30)]
        assert ctx.timezone == "Etc/UTC"
