from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]


class LoggingConfig(BaseModel):
    """Конфигурация логирования."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    level: LogLevel = Field(default="INFO", description="Уровень логирования")
    format: str = Field(
        default="{time:HH:mm:ss} | {level: <8} | {module}:{function}:{line} - {message} | {extra}",
        description="Формат логирования",
    )
    serialize: bool = Field(default=False, description="Сериализовать логирование")
    to_file: bool = Field(default=False, description="Включить файловое логирование")
    file_path: Path = Field(default="data/logs/wednesday.log", description="Путь к файлу лога")
    noisy_libs: list[str] = Field(
        default=["aiogram", "httpx", "sqlalchemy", "prometheus_client"],
        description="Библиотеки, которые генерируют много логов",
    )
