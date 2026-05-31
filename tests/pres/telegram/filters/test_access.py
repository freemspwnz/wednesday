"""Tests for AdminAccessFilter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.dto import UserContext
from domain.kernel.vo import NonEmptyStr
from domain.user import UserRole
from presentation.aiogram.filters.access import AdminAccessFilter


def _user(*, role: UserRole | None = UserRole.USER) -> UserContext:
    return UserContext(
        tg_id=1,
        is_bot=False,
        first_name=NonEmptyStr("Test"),
        role=role,
    )


@pytest.fixture
def admin_filter() -> AdminAccessFilter:
    logger = MagicMock()
    logger.bind.return_value = logger
    return AdminAccessFilter(logger=logger)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (_user(role=UserRole.USER), False),
        (_user(role=UserRole.ADMIN), True),
        (_user(role=UserRole.OWNER), True),
        (_user(role=None), False),
        (None, False),
    ],
)
async def test_admin_access_filter(
    admin_filter: AdminAccessFilter,
    user: UserContext | None,
    expected: bool,
) -> None:
    assert await admin_filter(event=MagicMock(), user=user) is expected
