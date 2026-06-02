"""Metrics export and HTTP server errors."""

from ..base import AppError


class MetricsError(AppError):
    """Base metrics infrastructure error."""


class MetricsExportError(MetricsError):
    """Failed to generate exposition (generate_latest)."""


class MetricsHttpExporterError(MetricsError):
    """Failed to start built-in HTTP metrics exporter (bind / listen)."""
