from pathlib import Path

from ..base import AppError, UnexpectedAppError


class CatalogError(AppError):
    """Base exception for YAML catalog persistence errors."""


class CatalogNotFoundError(CatalogError):
    """Catalog file is missing on disk."""

    def __init__(self, message: str, *, source: Path) -> None:
        super().__init__(message)
        self.source = source


class CatalogParseError(CatalogError):
    """Catalog file cannot be parsed as YAML."""

    def __init__(self, message: str, *, source: Path) -> None:
        super().__init__(message)
        self.source = source


class CatalogFormatError(CatalogError):
    """Catalog file has invalid structure or content."""

    def __init__(
        self,
        message: str,
        *,
        source: Path,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.field = field


class UnexpectedCatalogError(UnexpectedAppError):
    """Unexpected YAML catalog infrastructure error."""
