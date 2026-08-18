"""Tests for the root Config model and PROD validation."""

from importlib.metadata import version as pkg_version

import pytest
from pydantic import SecretStr, ValidationError

from infra.config import Config, GigaChatConfig
from infra.config.observe import LoggingConfig, MetricsConfig
from infra.config.persistence.postgres import PostgresConfig
from infra.config.persistence.redis import RedisConfig
from infra.config.presentation import TelegramConfig
from infra.config.resilience.asyncbreaker import CircuitBreakerConfig
from infra.config.resilience.limits import RateLimitConfig


@pytest.mark.unit
class TestConfigDefaults:
    def test_dev_defaults_load(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENV", raising=False)
        cfg = Config(_env_file=None, ENV="DEV", metrics=MetricsConfig(enabled=False))

        assert cfg.env == "DEV"
        assert cfg.version == pkg_version("wednesday")
        assert cfg.telegram.limiter.storage == "redis"
        assert cfg.telegram.retrier.name == "telegram"
        assert cfg.gigachat.limiter.storage == "redis"
        assert cfg.gigachat.breaker.storage == "redis"
        assert cfg.logging.serialize is False
        assert cfg.metrics.enabled is False

        cfg_override = Config(_env_file=None, VERSION="1.2.3")
        assert cfg_override.version == "1.2.3"

    def test_postgres_dsn_asyncpg_scheme(self) -> None:
        cfg = Config(
            _env_file=None,
            postgres=PostgresConfig(
                user="u",
                password=SecretStr("p"),
                db_name="db",
                host="localhost",
                port=5432,
            ),
        )
        assert cfg.postgres.dsn.startswith("postgresql+asyncpg://")

    def test_redis_dsn_from_components(self) -> None:
        cfg = Config(
            _env_file=None,
            redis=RedisConfig(password=SecretStr("secret")),
        )
        assert cfg.redis.dsn.startswith("redis://")


@pytest.mark.unit
class TestConfigProdValidation:
    def test_prod_accepts_valid_config(self, prod_config: Config) -> None:
        assert prod_config.env.upper() == "PROD"
        assert prod_config.logging.serialize is True
        assert prod_config.metrics.enabled is True
        assert prod_config.telegram.limiter.storage == "redis"
        assert prod_config.gigachat.limiter.storage == "redis"

    @pytest.mark.parametrize(
        ("kwargs", "fragment"),
        [
            ({"logging": LoggingConfig(serialize=False)}, "LOGGING__SERIALIZE"),
            ({"metrics": MetricsConfig(enabled=False)}, "METRICS__ENABLED"),
            ({"postgres": PostgresConfig(password=SecretStr("postgres"), echo=False)}, "POSTGRES__PASSWORD"),
            ({"postgres": PostgresConfig(password=SecretStr("x"), echo=True)}, "POSTGRES__ECHO"),
            ({"redis": RedisConfig(password=SecretStr("redis"))}, "REDIS__PASSWORD"),
            (
                {
                    "telegram": TelegramConfig(
                        token=SecretStr("prod-telegram-token"),
                        admin_id=1,
                        limiter=RateLimitConfig(storage="memory", name="telegram"),
                    ),
                },
                "TELEGRAM__LIMITER__STORAGE",
            ),
            (
                {
                    "gigachat": GigaChatConfig(
                        auth_key=SecretStr("prod-gigachat-auth-key"),
                        limiter=RateLimitConfig(storage="memory", name="gigachat"),
                    ),
                },
                "GIGACHAT__LIMITER__STORAGE",
            ),
            (
                {
                    "gigachat": GigaChatConfig(
                        auth_key=SecretStr("prod-gigachat-auth-key"),
                        breaker=CircuitBreakerConfig(storage="memory", name="gigachat"),
                    ),
                },
                "GIGACHAT__BREAKER__STORAGE",
            ),
            (
                {"gigachat": GigaChatConfig(auth_key=SecretStr("default"))},
                "GIGACHAT__AUTH_KEY",
            ),
        ],
    )
    def test_prod_rejects_invalid(
        self,
        prod_config_kwargs: dict[str, object],
        kwargs: dict[str, object],
        fragment: str,
    ) -> None:
        merged = {**prod_config_kwargs, **kwargs}
        with pytest.raises(ValidationError, match=fragment):
            Config(_env_file=None, **merged)  # type: ignore[arg-type]

    def test_non_prod_allows_dev_passwords(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENV", raising=False)
        cfg = Config(
            _env_file=None,
            ENV="DEV",
            postgres=PostgresConfig(password=SecretStr("postgres")),
            redis=RedisConfig(password=SecretStr("redis")),
            metrics=MetricsConfig(enabled=False),
        )
        assert cfg.postgres.password.get_secret_value() == "postgres"
