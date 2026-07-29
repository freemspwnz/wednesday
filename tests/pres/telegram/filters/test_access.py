"""Tests for AdminAccessFilter."""

from unittest.mock import MagicMock

import pytest

from domain.user import UserRole
from presentation.aiogram.filters.access import AdminAccessFilter

from ..factories import mk_user_context


@pytest.fixture
def admin_filter() -> AdminAccessFilter:
    logger = MagicMock()
    logger.bind.return_value = logger
    return AdminAccessFilter(logger=logger)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.USER, False),
        (UserRole.ADMIN, True),
        (UserRole.OWNER, True),
    ],
)
async def test_admin_access_filter_by_role(
    admin_filter: AdminAccessFilter,
    role: UserRole,
    expected: bool,
) -> None:
    user = mk_user_context(role=role)
    assert await admin_filter(event=MagicMock(), user=user) is expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_admin_access_filter_rejects_none_user(admin_filter: AdminAccessFilter) -> None:
    assert await admin_filter(event=MagicMock(), user=None) is False
