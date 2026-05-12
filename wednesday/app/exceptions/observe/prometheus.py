"""Ошибки, связанные с экспортом и HTTP-сервером Prometheus (observe)."""

from ..base import AppError


class PrometheusObserveError(AppError):
    """Базовая ошибка инфраструктурного слоя метрик Prometheus."""


class PrometheusExportError(PrometheusObserveError):
    """Не удалось сформировать exposition (generate_latest)."""


class PrometheusHttpExporterError(PrometheusObserveError):
    """Не удалось запустить встроенный HTTP-экспортёр метрик (bind / listen)."""
