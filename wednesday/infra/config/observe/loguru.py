from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]


class LoggingConfig(BaseModel):
    """Logging configuration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    level: LogLevel = Field(default="INFO", description="Logging level")
    format: str = Field(
        default="{time:HH:mm:ss} | {level: <8} | {module}:{function}:{line} - {message} | {extra}",
        description="Logging format",
    )
    serialize: bool = Field(default=False, description="Serialize logging")
    to_file: bool = Field(default=False, description="Enable file logging")
    file_path: Path = Field(default=Path("data/logs/wednesday.log"), description="Path to the log file")
    noisy_libs: list[str] = Field(
        default=["aiogram", "httpx", "sqlalchemy", "prometheus_client"],
        description="Libraries that generate a lot of logs",
    )
