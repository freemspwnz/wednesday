"""Redis connection settings loaded from environment (nested ``REDIS__*``)."""

from __future__ import annotations

from functools import cached_property

from pydantic import BaseModel, ConfigDict, Field, RedisDsn, SecretStr, computed_field, model_validator


class RedisConfig(BaseModel):
    """Validated Redis URL and pool/socket limits for ``redis.asyncio``."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    url: RedisDsn | None = Field(default=None, description="Full redis URL (overrides host/port/password)")
    host: str = Field(default="localhost", min_length=1, description="Redis host")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    db: int = Field(default=0, ge=0, description="Redis logical database number")
    password: SecretStr = Field(description="Redis password")

    decode_responses: bool = Field(default=True, description="Decode responses from Redis to Python objects")
    max_connections: int = Field(default=10, ge=1, le=50_000, description="Maximum number of connections to Redis")
    socket_timeout: float = Field(default=10.0, gt=0.0, le=86400.0, description="Timeout for socket operations")

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def dsn(self) -> str:
        """Connection string for ``Redis.from_url`` (built from ``url`` or host/port/password)."""
        if self.url is not None:
            return str(self.url)
        return str(
            RedisDsn.build(
                scheme="redis",
                password=self.password.get_secret_value(),
                host=self.host,
                port=self.port,
                path=f"{self.db}",
            )
        )

    @model_validator(mode="after")
    def validate_dsn_components(self) -> RedisConfig:
        """Reject unusable combinations when building DSN from discrete fields."""
        if self.url is not None:
            return self
        if not self.host.strip():
            msg = "REDIS__HOST must be non-empty when REDIS__URL is not set"
            raise ValueError(msg)
        return self
