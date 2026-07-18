"""Tests for RateLimitRequestMW key helpers."""

import pytest

from presentation.aiogram.middlewares.bot.limiter import RateLimitRequestMW


@pytest.mark.unit
def test_outbound_rate_limit_keys() -> None:
    assert RateLimitRequestMW._rl_outbound_chat_key(-1001) == "group:-1001"
    assert RateLimitRequestMW._rl_outbound_user_key(42) == "user:42"
    assert "rl:" not in RateLimitRequestMW._rl_outbound_chat_key(1)
