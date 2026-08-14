from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HttpTimeoutConfig(BaseModel):
    """Http timeout configuration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    timeout: int = Field(default=60, description="Overall request timeout in seconds")
    connect: int = Field(default=10, description="Connection establishment timeout in seconds")
    read: int = Field(default=60, description="Socket read timeout in seconds")
    write: int = Field(default=30, description="Socket write timeout in seconds")
    pool: int = Field(default=10, description="Timeout waiting for a free connection pool slot in seconds")


class HttpConfig(BaseModel):
    """Http client configuration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )
    name: str = Field(default="default", description="Client name")
    base_url: str = Field(default="", description="Base URL for all requests")

    headers: dict[str, str] | None = Field(
        default={"User-Agent": "wednesday/7.4.0"},
        description="Default headers for all requests",
    )
    verify: bool | str = Field(default=True, description="SSL certificate verification")
    http2: bool = Field(default=True, description="Use HTTP/2")
    follow_redirects: bool = Field(default=True, description="Follow redirects")

    max_connections: int = Field(default=200, description="Maximum number of connections")
    max_keepalive_connections: int = Field(default=50, description="Maximum number of keepalive connections")
    keepalive_expiry: int = Field(default=30, description="Keepalive connection lifetime in seconds")

    timeouts: dict[str, HttpTimeoutConfig] = Field(
        default={"base": HttpTimeoutConfig()},
        description="Timeouts for all requests",
    )

    @field_validator("verify", mode="before")
    @classmethod
    def _validate_cert_path(cls, v: bool | str) -> bool | str:
        if isinstance(v, str):
            cert_file = Path(v)
            if cert_file.exists():
                return str(cert_file.absolute())
            raise ValueError(f"Certificate file {v} does not exist")
        return v
