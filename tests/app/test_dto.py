from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.dto import ChatContext, UserContext
from domain.chat import Chat, ChatId, ChatProfile, ChatSchedule, ChatScheduleSet, ChatType, Weekday
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole, UserSubscription


def _dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


@pytest.mark.unit
def test_user_context_from_domain_maps_new_aggregate_shape() -> None:
    user = User.register(
        id=UserId(UUID(int=101)),
        profile=UserProfile(
            telegram_id=123456,
            is_bot=False,
            first_name=NonEmptyStr("Alice"),
            last_name=NonEmptyStr("Smith"),
            username="alice",
            language_code="en",
            has_tg_premium=True,
        ),
        role=UserRole.ADMIN,
        subscription=UserSubscription.premium(_dt(10)),
        now=_dt(10),
    )
    user.ban(actor=UserRole.OWNER, until=_dt(12), at=_dt(11))

    ctx = UserContext.from_domain(user)

    assert ctx.id == user.id
    assert ctx.tg_id == 123456
    assert ctx.has_tg_premium is True
    assert ctx.is_banned is True
    assert isinstance(ctx.banned_until, AwareDatetime)
    assert ctx.subscription_tier == user.subscription.plan.tier
    assert ctx.subscription_daily_limit == user.subscription.plan.daily_limit


@pytest.mark.unit
def test_chat_context_from_domain_maps_schedule_fields() -> None:
    chat = Chat.register(
        id=ChatId(UUID(int=202)),
        profile=ChatProfile(
            type=ChatType.GROUP,
            telegram_id=-100500,
            title="Team",
            username="team_chat",
        ),
        schedules=ChatScheduleSet(
            timezone=ZoneInfo("UTC"),
            weekday=Weekday.MONDAY,
            schedules=(ChatSchedule(hour=9, minute=0), ChatSchedule(hour=12, minute=30)),
        ),
        at=_dt(9),
    )

    ctx = ChatContext.from_domain(chat)

    assert ctx.id == chat.id
    assert ctx.tg_id == -100500
    assert ctx.type == ChatType.GROUP
    assert ctx.timezone == ZoneInfo("UTC")
    assert ctx.weekday == Weekday.MONDAY
    assert ctx.schedules == chat.schedules.schedules
