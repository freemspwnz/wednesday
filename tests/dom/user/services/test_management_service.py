"""Tests for UserManagementService."""

from unittest.mock import AsyncMock

import pytest

from domain.user import UserManagementService, UserRole
from tests.dom.user.factories import dt

from .test_lifecycle_service import mk_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_change_role_persists_via_repo() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user

    await UserManagementService.change_role(
        id=user.id,
        actor=UserRole.OWNER,
        new_role=UserRole.ADMIN,
        repo=repo,
        at=dt(11),
    )

    repo.save.assert_awaited_once_with(user)
    assert user.role == UserRole.ADMIN
