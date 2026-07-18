from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..network import HttpConfig, HttpTimeoutConfig
from ..resilience import CircuitBreakerConfig, RateLimitConfig, RetryConfig


class GigaChatConfig(BaseModel):
    """GigaChat configuration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    auth_url: str = Field(
        default="https://ngw.devices.sberbank.ru:9443/api/v2/oauth", description="Authentication URL for GigaChat API"
    )
    auth_key: SecretStr = Field(default=SecretStr("default"), description="Authentication key for GigaChat API")
    scope: str = Field(default="GIGACHAT_API_PERS", description="Scope for GigaChat API")

    http: HttpConfig = Field(
        default=HttpConfig(
            base_url="https://gigachat.devices.sberbank.ru/api/v1/",
            timeouts={
                "base": HttpTimeoutConfig(
                    timeout=30,
                    connect=10,
                    read=30,
                    write=30,
                    pool=10,
                ),
                "image": HttpTimeoutConfig(
                    timeout=120,
                    connect=10,
                    read=120,
                    write=30,
                    pool=10,
                ),
                "prompt": HttpTimeoutConfig(
                    timeout=60,
                    connect=10,
                    read=60,
                    write=30,
                    pool=10,
                ),
                "models": HttpTimeoutConfig(
                    timeout=30,
                    connect=10,
                    read=30,
                    write=30,
                    pool=10,
                ),
            },
            max_connections=10,
            max_keepalive_connections=10,
            keepalive_expiry=10,
            headers={"User-Agent": "wednesday/7.2.0"},
            verify=True,
            http2=True,
            follow_redirects=True,
        )
    )

    retrier: RetryConfig = Field(
        default=RetryConfig(
            name="gigachat",
            attempts=3,
            reraise=True,
            initial=2.0,
            max=60.0,
            exp_base=2.0,
            jitter=1,
        )
    )

    limiter: RateLimitConfig = Field(
        default=RateLimitConfig(
            name="gigachat",
            storage="redis",
            strategy="sliding-window-counter",
            limits={
                "base": "1/second",
            },
        )
    )

    breaker: CircuitBreakerConfig = Field(
        default=CircuitBreakerConfig(
            name="gigachat",
            threshold=6,
            cooldown=timedelta(seconds=60),
            storage="redis",
        )
    )
