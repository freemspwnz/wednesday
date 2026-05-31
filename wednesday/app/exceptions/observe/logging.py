from typing import Any

from ..base import AppError


class LoggingError(AppError):
    """Base logging error."""


class LogMessageFormatError(LoggingError):
    """Formatting template is invalid for log arguments."""

    def __init__(self, template: str, log_args: tuple[Any, ...]) -> None:
        super().__init__(f"Invalid log message format: template={template}, args={log_args}")
        self.template = template
        self.log_args = log_args
