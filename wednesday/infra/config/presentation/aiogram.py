from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..resilience import RateLimitConfig, RetryConfig


class TelegramConfig(BaseModel):
    """Configuration for Telegram bot."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    token: SecretStr = Field(default=SecretStr("token"), description="Telegram bot token")
    admin_id: int = Field(default=0, description="Telegram admin ID")
    proxy_url: SecretStr | None = Field(
        default=None,
        description="Optional HTTP proxy for the Telegram session. Empty means direct.",
    )

    @field_validator("proxy_url", mode="before")
    @classmethod
    def _normalize_proxy_url(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            raw = value.get_secret_value()
        elif isinstance(value, str):
            raw = value
        else:
            raise ValueError("TELEGRAM__PROXY_URL must be an http URL")
        if raw == "":
            return None
        parsed = urlparse(raw)
        if parsed.scheme != "http" or parsed.hostname is None:
            raise ValueError("TELEGRAM__PROXY_URL must be an http URL with a host")
        return raw

    retrier: RetryConfig = Field(
        default=RetryConfig(
            name="telegram",
            attempts=3,
            reraise=True,
            max=30,
            exp_base=2.0,
            jitter=1,
            initial=2.0,
        ),
    )

    limiter: RateLimitConfig = Field(
        default=RateLimitConfig(
            name="telegram",
            storage="redis",
            strategy="sliding-window-counter",
            limits={
                "global": "30/second",
                "user": "3/second",
                "chat": "30/minute",
                "throttling": "1 per 5 seconds",
            },
        ),
    )
