from __future__ import annotations

from typing import Any, cast

import pytest

from domain.user import UserBanned, UserModerationService
from domain.user.exceptions import ValidationError
from domain.user.policies import NoBan, ViolationStats

from ..factories import FakeViolationRepo, dt, mk_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_moderation_service_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))
    await UserModerationService.assign_ban(
        user=user,
        repo=FakeViolationRepo(stats=ViolationStats(hour=0, today=0, week=0, total=0)),
        at=dt(12),
    )
    assert user.pull_events() == []

    await UserModerationService.assign_ban(
        user=user,
        repo=FakeViolationRepo(stats=ViolationStats(hour=2, today=2, week=2, total=2)),
        at=dt(12),
    )
    assert isinstance(user.pull_events()[0], UserBanned)

    monkeypatch.setattr(
        "domain.user.services.moderation.BanDurationPolicy.evaluate",
        lambda **_: cast(Any, object()),
    )
    with pytest.raises(ValidationError):
        await UserModerationService.assign_ban(
            user=user,
            repo=FakeViolationRepo(stats=ViolationStats(hour=0, today=0, week=0, total=0)),
            at=dt(12),
        )

    with pytest.raises(ValidationError):
        await UserModerationService.assign_ban(
            user="bad",  # type: ignore[arg-type]
            repo=FakeViolationRepo(),
            at=dt(12),
        )

    with pytest.raises(ValidationError):
        await UserModerationService.assign_ban(
            user=user,
            repo=cast(Any, "bad"),
            at=dt(12),
        )

    monkeypatch.setattr(
        "domain.user.services.moderation.BanDurationPolicy.evaluate",
        lambda **_: NoBan(),
    )
    await UserModerationService.assign_ban(
        user=user,
        repo=FakeViolationRepo(stats=ViolationStats(hour=0, today=0, week=0, total=0)),
        at=dt(12),
    )
