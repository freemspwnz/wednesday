from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..resilience import RateLimitConfig, RetryConfig


class TelegramConfig(BaseModel):
    """Configuration for Telegram bot."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    token: SecretStr = Field(default=SecretStr("token"), description="Telegram bot token")
    admin_id: int = Field(default=0, description="Telegram admin ID")

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
