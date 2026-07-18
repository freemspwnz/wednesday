"""Fixtures for infra.config tests."""

import pytest
from pydantic import SecretStr

from infra.config import Config, GigaChatConfig
from infra.config.observe import LoggingConfig, MetricsConfig
from infra.config.persistence.postgres import PostgresConfig
from infra.config.persistence.redis import RedisConfig
from infra.config.presentation import TelegramConfig


@pytest.fixture
def prod_config_kwargs() -> dict[str, object]:
    return {
        "ENV": "PROD",
        "logging": LoggingConfig(serialize=True),
        "metrics": MetricsConfig(enabled=True),
        "postgres": PostgresConfig(password=SecretStr("prod-postgres-secret"), echo=False),
        "redis": RedisConfig(password=SecretStr("prod-redis-secret")),
        "telegram": TelegramConfig(
            token=SecretStr("prod-telegram-token"),
            admin_id=1,
        ),
        "gigachat": GigaChatConfig(
            auth_key=SecretStr("prod-gigachat-auth-key"),
        ),
    }


@pytest.fixture
def prod_config(prod_config_kwargs: dict[str, object]) -> Config:
    return Config(_env_file=None, **prod_config_kwargs)  # type: ignore[arg-type]
