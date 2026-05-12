from pydantic import BaseModel, ConfigDict, Field


class MetricsConfig(BaseModel):
    """Configuration for prometheus HTTP server."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    enabled: bool = Field(default=False, description="Enable/disable prometheus HTTP server")
    host: str = Field(default="0.0.0.0", description="Host to listen on")
    port: int = Field(default=8080, description="Port to listen on")
