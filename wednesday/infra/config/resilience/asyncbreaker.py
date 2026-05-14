from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaker."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: str = Field(default="unknown", description="Name for circuit breaker")
    threshold: int = Field(default=6, gt=0, description="Threshold for circuit breaker")
    cooldown: timedelta = Field(default=timedelta(seconds=60), description="Cooldown for circuit breaker")
    storage: Literal["redis", "memory"] = Field(default="memory", description="Storage for circuit breaker")

    @field_validator("cooldown", mode="before")
    @classmethod
    def _to_timedelta(cls, v: int | str) -> timedelta:
        if isinstance(v, int | str):
            return timedelta(seconds=int(v))
        return v
