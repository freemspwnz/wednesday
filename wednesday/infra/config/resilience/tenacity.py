from pydantic import BaseModel, ConfigDict, Field


class RetryConfig(BaseModel):
    """Конфигурация для retry‑механизмов."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: str = Field(default="unknown", description="Name of the retrier instance.")
    attempts: int = Field(default=3, description="Number of attempts to retry the operation.")
    reraise: bool = Field(default=True, description="Whether to reraise the exception if the operation fails.")
    initial: float = Field(default=2.0, description="Initial time to wait between attempts.")
    max: float = Field(default=60.0, description="Maximum time to wait between attempts.")
    exp_base: float = Field(default=2.0, description="Base of the exponential backoff.")
    jitter: float = Field(default=1, description="Jitter to add to the backoff.")
