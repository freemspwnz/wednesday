"""Tests for presentation.aiogram.middlewares.utils (shared helpers)."""

from unittest.mock import MagicMock

import pytest

from presentation.aiogram.middlewares.utils import (
    is_chat,
    is_request_scope,
    require_request_scope,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("chat_id", "expected"),
    [(-100123, True), (12345, False), ("-100abc", True)],
)
def test_is_chat(chat_id: int | str, expected: bool) -> None:
    assert is_chat(chat_id) is expected


def _valid_scope() -> MagicMock:
    scope = MagicMock()
    scope.user_lifecycle_uc = MagicMock()
    scope.user_management_uc = MagicMock()
    scope.user_moderation_uc = MagicMock()
    scope.user_generation_uc = MagicMock()
    scope.chat_management_uc = MagicMock()
    scope.chat_schedule_uc = MagicMock()
    scope.logger = MagicMock()
    return scope


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scope", "error_match"),
    [(None, "missing"), (object(), "Invalid request scope")],
)
def test_require_request_scope_raises(scope: object | None, error_match: str) -> None:
    with pytest.raises((RuntimeError, TypeError), match=error_match):
        require_request_scope(scope)


@pytest.mark.unit
def test_require_request_scope_ok() -> None:
    scope = _valid_scope()
    assert is_request_scope(scope) is True
    assert require_request_scope(scope) is scope
