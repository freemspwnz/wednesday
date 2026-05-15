"""Тесты factory и парсинга limits."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.config.resilience.limits import RateLimitConfig
from infra.resilience.limits.limiter import Limits
from infra.resilience.limits.setup import _limits, rl_factory


@pytest.mark.unit
class TestParseLimits:
    def test_namespaces_include_config_name(self) -> None:
        items = _limits(
            "telegram",
            {"global": "30/second", "user": "1/second"},
        )

        assert set(items) == {"global", "user"}
        assert items["global"].namespace == "telegram:global"
        assert items["user"].namespace == "telegram:user"


@pytest.mark.unit
class TestRlFactory:
    def test_memory_factory_returns_limits_with_parsed_items(self) -> None:
        log = MagicMock()
        log.bind.return_value = log
        config = RateLimitConfig(
            name="unit",
            storage="memory",
            strategy="fixed-window",
            limits={"base": "5/minute"},
        )

        rl = rl_factory(
            config=config,
            env="test",
            version="0.0.0",
            redis_dsn="redis://localhost",
            redis_pool=MagicMock(),
            metrics=MagicMock(),
            logger=log,
        )

        assert isinstance(rl, Limits)
        assert "base" in rl.limits
        assert rl.limits["base"].namespace == "unit:base"
        log.debug.assert_called_once()
