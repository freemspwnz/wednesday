from __future__ import annotations

from typing import Any, cast

import pytest

from domain.user import UserBanned, UserModerationService, UserNotFoundError
from domain.user.exceptions import ValidationError
from domain.user.policies import NoBan, ViolationStats

from ..factories import FakeUserRepo, FakeViolationRepo, dt, mk_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assign_ban_records_violation_without_ban_under_threshold() -> None:
    user = mk_user(now=dt(10))
    user_repo = FakeUserRepo.with_users(user)
    violations = FakeViolationRepo(stats=ViolationStats(hour=0, today=0, week=0, total=0))

    result = await UserModerationService.assign_ban(
        user_id=user.id,
        user_repo=user_repo,
        violation_repo=violations,
        at=dt(12),
    )

    assert result.pull_events() == []
    assert violations.stats == ViolationStats(hour=1, today=1, week=1, total=1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assign_ban_bans_when_threshold_reached_after_record() -> None:
    user = mk_user(now=dt(10))
    user_repo = FakeUserRepo.with_users(user)
    # hour=1 → after record hour=2 → BanDurationPolicy hourly threshold
    violations = FakeViolationRepo(stats=ViolationStats(hour=1, today=1, week=1, total=1))

    result = await UserModerationService.assign_ban(
        user_id=user.id,
        user_repo=user_repo,
        violation_repo=violations,
        at=dt(12),
    )

    assert isinstance(result.pull_events()[0], UserBanned)
    assert violations.stats == ViolationStats(hour=2, today=2, week=2, total=2)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moderation_service_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))
    user_repo = FakeUserRepo.with_users(user)

    monkeypatch.setattr(
        "domain.user.services.moderation.BanDurationPolicy.evaluate",
        lambda **_: cast(Any, object()),
    )
    with pytest.raises(ValidationError):
        await UserModerationService.assign_ban(
            user_id=user.id,
            user_repo=user_repo,
            violation_repo=FakeViolationRepo(stats=ViolationStats(hour=0, today=0, week=0, total=0)),
            at=dt(12),
        )

    with pytest.raises(ValidationError):
        await UserModerationService.assign_ban(
            user_id="bad",  # type: ignore[arg-type]
            user_repo=user_repo,
            violation_repo=FakeViolationRepo(),
            at=dt(12),
        )

    with pytest.raises(ValidationError):
        await UserModerationService.assign_ban(
            user_id=user.id,
            user_repo=cast(Any, "bad"),
            violation_repo=FakeViolationRepo(),
            at=dt(12),
        )

    with pytest.raises(UserNotFoundError):
        await UserModerationService.assign_ban(
            user_id=mk_user(user_id=99, now=dt(10)).id,
            user_repo=FakeUserRepo.with_users(user),
            violation_repo=FakeViolationRepo(),
            at=dt(12),
        )

    monkeypatch.setattr(
        "domain.user.services.moderation.BanDurationPolicy.evaluate",
        lambda **_: NoBan(),
    )
    violations = FakeViolationRepo(stats=ViolationStats(hour=0, today=0, week=0, total=0))
    result = await UserModerationService.assign_ban(
        user_id=user.id,
        user_repo=user_repo,
        violation_repo=violations,
        at=dt(12),
    )
    assert result.pull_events() == []
    assert violations.stats.total == 1
