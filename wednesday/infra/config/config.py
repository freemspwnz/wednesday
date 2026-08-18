from importlib.metadata import version as _pkg_version
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .integrations import GigaChatConfig
from .observe import LoggingConfig, MetricsConfig
from .persistence import PostgresConfig, RedisConfig, YamlConfig
from .presentation import TelegramConfig


class Config(BaseSettings):
    """Main configuration model.
    Contains all nested configuration models for different modules.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__",
    )

    env: str = Field(default="DEV", alias="ENV")
    version: str = Field(default_factory=lambda: _pkg_version("wednesday"), alias="VERSION")

    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    gigachat: GigaChatConfig = Field(default_factory=GigaChatConfig)

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    yaml: YamlConfig = Field(default_factory=YamlConfig)

    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)

    @model_validator(mode="after")
    def validate_prod_env(self) -> Self:
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
        if self.telegram.token.get_secret_value() == "token":
            errors.append("TELEGRAM__TOKEN must be set in PROD")
        if self.telegram.admin_id == 0:
            errors.append("TELEGRAM__ADMIN_ID must be set in PROD")
        if self.telegram.limiter.storage != "redis":
            errors.append("TELEGRAM__LIMITER__STORAGE must be redis in PROD")
        if self.gigachat.breaker.storage != "redis":
            errors.append("GIGACHAT__BREAKER__STORAGE must be redis in PROD")
        if self.gigachat.limiter.storage != "redis":
            errors.append("GIGACHAT__LIMITER__STORAGE must be redis in PROD")
        if self.gigachat.auth_key.get_secret_value() == "default":
            errors.append("GIGACHAT__AUTH_KEY must be set in PROD")

        if errors:
            raise ValueError("\n".join(errors))

        return self
