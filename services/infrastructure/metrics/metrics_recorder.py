"""Сервис для записи метрик.

Обёртка над utils.metrics.Metrics, реализующая протокол IMetrics.
"""

from __future__ import annotations

from typing import Any

from services.base.base_service import BaseService
from services.protocols import IMetrics
from utils.metrics import Metrics


class MetricsRecorder(BaseService, IMetrics):
    """Сервис для записи метрик.

    Реализует протокол IMetrics, оборачивая utils.metrics.Metrics.
    Добавляет логирование всех записей метрик.
    """

    def __init__(self, metrics: Metrics | None = None) -> None:
        """Инициализирует сервис записи метрик.

        Args:
            metrics: Экземпляр Metrics для записи метрик. Если None, создаётся новый.
        """
        super().__init__()
        from utils.postgres_client import get_postgres_pool

        self._metrics = metrics or Metrics(pool=get_postgres_pool())

    async def increment_generation_success(self) -> None:
        """Увеличивает счётчик успешных генераций изображений."""
        try:
            await self._metrics.increment_generation_success()
            self.log_event(
                event="metric_recorded",
                status="success",
                level="debug",
                message="Записана метрика: increment_generation_success",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_generation_success: {e}")

    async def increment_generation_failed(self) -> None:
        """Увеличивает счётчик неудачных генераций изображений."""
        try:
            await self._metrics.increment_generation_failed()
            self.log_event(
                event="metric_recorded",
                status="failed",
                level="debug",
                message="Записана метрика: increment_generation_failed",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_generation_failed: {e}")

    async def increment_cache_hit(self) -> None:
        """Увеличивает счётчик попаданий в кэш."""
        try:
            # В текущей реализации Metrics нет метода increment_cache_hit,
            # но мы можем использовать record_metric для записи события
            from utils.metrics import record_metric

            await record_metric(event_type="cache_hit", status="hit")
            self.log_event(
                event="metric_recorded",
                status="cache_hit",
                level="debug",
                message="Записана метрика: increment_cache_hit",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_cache_hit: {e}")

    async def increment_dispatch_success(self) -> None:
        """Увеличивает счётчик успешных отправок сообщений."""
        try:
            await self._metrics.increment_dispatch_success()
            self.log_event(
                event="metric_recorded",
                status="success",
                level="debug",
                message="Записана метрика: increment_dispatch_success",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_dispatch_success: {e}")

    async def increment_dispatch_failed(self) -> None:
        """Увеличивает счётчик неудачных отправок сообщений."""
        try:
            await self._metrics.increment_dispatch_failed()
            self.log_event(
                event="metric_recorded",
                status="failed",
                level="debug",
                message="Записана метрика: increment_dispatch_failed",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_dispatch_failed: {e}")

    async def record_circuit_breaker_trip(self) -> None:
        """Увеличивает счётчик срабатываний circuit breaker."""
        try:
            await self._metrics.increment_circuit_breaker_trip()
            self.log_event(
                event="metric_recorded",
                status="circuit_breaker_trip",
                level="debug",
                message="Записана метрика: record_circuit_breaker_trip",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики record_circuit_breaker_trip: {e}")

    async def get_summary(self) -> dict[str, Any]:
        """Возвращает сводку всех метрик производительности."""
        try:
            return await self._metrics.get_summary()
        except Exception as e:
            self.logger.warning(f"Ошибка при получении сводки метрик: {e}")
            # Возвращаем пустую сводку при ошибке
            return {
                "generations_total": 0,
                "generations_success": 0,
                "generations_failed": 0,
                "generations_retries": 0,
                "average_generation_time": "0.00s",
                "dispatches_success": 0,
                "dispatches_failed": 0,
                "circuit_breaker_trips": 0,
            }
