from typing import Any, Self

from loguru import logger

from app.exceptions import LogMessageFormatError
from app.protocols import Logger
from infra.config import LoggingConfig

from .setup import setup_logging


class LoguruLogger(Logger):
    """Loguru adapter implementing the Logger protocol."""

    __slots__ = ("_bound_context", "_core")

    def __init__(self, core: Any, bound_context: dict[str, object] | None = None) -> None:  # noqa: ANN401
        self._core = core
        self._bound_context = {"module": "unknown", **(bound_context or {})}

    def trace(self, message: str, *args: object, **kwargs: object) -> None:
        self._log("TRACE", message, *args, **kwargs)

    def debug(self, message: str, *args: object, **kwargs: object) -> None:
        self._log("DEBUG", message, *args, **kwargs)

    def info(self, message: str, *args: object, **kwargs: object) -> None:
        self._log("INFO", message, *args, **kwargs)

    def success(self, message: str, *args: object, **kwargs: object) -> None:
        self._log("SUCCESS", message, *args, **kwargs)

    def warning(self, message: str, *args: object, **kwargs: object) -> None:
        self._log("WARNING", message, *args, **kwargs)

    def error(self, message: str, *args: object, **kwargs: object) -> None:
        self._log("ERROR", message, *args, **kwargs)

    def critical(self, message: str, *args: object, **kwargs: object) -> None:
        self._log("CRITICAL", message, *args, **kwargs)

    def exception(self, message: str, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("exc_info", True)
        self._log("ERROR", message, *args, **kwargs)

    def log(self, level: str, message: str, *args: object, **kwargs: object) -> None:
        self._log(level, message, *args, **kwargs)

    def bind(self, **kwargs: object) -> Self:
        """Create a new logger instance with bound context."""
        return self.__class__(
            self._core,
            bound_context={**self._bound_context, **kwargs},
        )

    def _log(self, level: str, message: str, *args: object, **kwargs: object) -> None:
        """Main log routing method."""
        # 1. Format the message (stdlib logging style)
        if args:
            try:
                message = message.format(*args)
            except (ValueError, IndexError, KeyError) as e:
                raise LogMessageFormatError(message, args) from e

        # 2. Prepare context (extra fields)
        # Merge bound context from bind() with current kwargs
        payload = {**self._bound_context, **kwargs}

        # Extract structured logging fields
        exc_info = payload.pop("exc_info", None)

        # 3. Forward to Loguru
        # Use opt(depth=2) so Loguru reports the caller file/line correctly
        self._core.opt(depth=2, exception=exc_info).bind(**payload).log(level, message)


def get_logger(
    *,
    config: LoggingConfig,
    env: str,
    version: str,
    secrets: list[str],
) -> Logger:
    """Factory for a typed logger instance."""
    setup_logging(config, env, version, secrets)
    return LoguruLogger(logger)
