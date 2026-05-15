"""Фикстуры для тестов infra.config."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from infra.config import Config
from infra.config.observe import LoggingConfig, MetricsConfig
from infra.config.persistence.postgres import PostgresConfig
from infra.config.persistence.redis import RedisConfig
from infra.config.resilience.asyncbreaker import CircuitBreakerConfig
from infra.config.resilience.limits import RateLimitConfig


@pytest.fixture
def prod_config_kwargs() -> dict[str, object]:
    return {
        "ENV": "PROD",
        "logging": LoggingConfig(serialize=True),
        "metrics": MetricsConfig(enabled=True),
        "postgres": PostgresConfig(password=SecretStr("prod-postgres-secret"), echo=False),
        "redis": RedisConfig(password=SecretStr("prod-redis-secret")),
        "rate_limit": RateLimitConfig(storage="redis"),
        "circuit_breaker": CircuitBreakerConfig(storage="redis"),
    }


@pytest.fixture
def prod_config(prod_config_kwargs: dict[str, object]) -> Config:
    return Config(_env_file=None, **prod_config_kwargs)  # type: ignore[arg-type]
