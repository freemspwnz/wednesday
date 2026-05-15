from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .observe import LoggingConfig, MetricsConfig
from .persistence import PostgresConfig, RedisConfig
from .resilience import CircuitBreakerConfig, RateLimitConfig, RetryConfig


class Config(BaseSettings):
    """Main configuration model.
    Contains all nested configuration models for different modules.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True, env_nested_delimiter="__"
    )

    env: str = Field(default="DEV", alias="ENV")
    version: str = Field(default="7.0.0", alias="VERSION")

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)

    retry: RetryConfig = Field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)

    @model_validator(mode="after")
    def validate_prod_env(self) -> Config:
        if self.env.upper() != "PROD":
            return self

        errors: list[str] = []

        if not self.logging.serialize:
            errors.append("LOGGING__SERIALIZE must be True in PROD")
        if not self.metrics.enabled:
            errors.append("METRICS__ENABLED must be True in PROD")
        if self.postgres.echo:
            errors.append("POSTGRES__ECHO must be False in PROD")
        if self.postgres.password.get_secret_value() == "postgres":
            errors.append("POSTGRES__PASSWORD must be set in PROD")
        if self.redis.password.get_secret_value() == "redis":
            errors.append("REDIS__PASSWORD must be set in PROD")
        if self.rate_limit.storage != "redis":
            errors.append("RATE_LIMIT__STORAGE must be redis in PROD")
        if self.circuit_breaker.storage != "redis":
            errors.append("CIRCUIT_BREAKER__STORAGE must be redis in PROD")

        if errors:
            raise ValueError("\n".join(errors))

        return self
