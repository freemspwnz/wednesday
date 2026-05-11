from typing import Any

from ..base import AppError


class LogMessageFormatError(AppError):
    """Formatting template is invalid for log arguments."""

    def __init__(self, template: str, args: tuple[Any, ...]) -> None:
        self.template = template
        self.args = args
        super().__init__(f"Invalid log message format: template={template}, args={args}")
