"""Ошибки экспорта и HTTP-сервера метрик (observe)."""

from ..base import AppError


class MetricsError(AppError):
    """Базовая ошибка инфраструктурного слоя метрик."""


class MetricsExportError(MetricsError):
    """Не удалось сформировать exposition (generate_latest)."""


class MetricsHttpExporterError(MetricsError):
    """Не удалось запустить встроенный HTTP-экспортёр метрик (bind / listen)."""
