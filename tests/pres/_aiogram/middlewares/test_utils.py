"""Тесты presentation.aiogram.middlewares.utils."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from presentation.aiogram.middlewares.utils import (
    is_chat,
    is_request_scope,
    require_request_scope,
    rl_global_key,
    rl_outbound_chat_key,
    rl_outbound_user_key,
    rl_throttle_key,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("chat_id", "expected"),
    [(-100123, True), (12345, False), ("-100abc", True)],
)
def test_is_chat(chat_id: int | str, expected: bool) -> None:
    assert is_chat(chat_id) is expected


@pytest.mark.unit
def test_rate_limit_keys() -> None:
    assert rl_global_key() == "global"
    assert rl_outbound_chat_key(-1001) == "group:-1001"
    assert rl_outbound_user_key(42) == "user:42"
    assert rl_throttle_key(99) == "throttle:99"
    assert "rl:" not in rl_outbound_chat_key(1)


def _valid_scope() -> MagicMock:
    scope = MagicMock()
    scope.registration_uc = MagicMock()
    scope.user_commands_uc = MagicMock()
    scope.chat_commands_uc = MagicMock()
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
