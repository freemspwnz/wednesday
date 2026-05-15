from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

STRATEGY = Literal[
    "fixed-window",
    "moving-window",
    "sliding-window-counter",
]


class RateLimitConfig(BaseModel):
    """Configuration for rate limiting."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: str = Field(default="unknown", description="Name for rate limiter")
    storage: Literal["redis", "memory"] = Field(default="memory", description="Storage type for rate limiter")
    strategy: STRATEGY = Field(default="sliding-window-counter", description="Strategy for rate limiter")
    limits: dict[str, str] = Field(default={"base_limit": "1/second"}, description="Limits dictionary for rate limiter")
