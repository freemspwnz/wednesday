"""Сервис для записи метрик.

Обёртка над utils.metrics.Metrics, реализующая протокол IMetrics.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from infra.metrics.metrics import Metrics
from shared.base.base_service import BaseService
from shared.protocols import ILogger, IMetrics


class MetricsRecorder(BaseService, IMetrics):
    """Сервис для записи метрик.

    Реализует протокол IMetrics, оборачивая utils.metrics.Metrics.
    Добавляет логирование всех записей метрик.
    """

    def __init__(self, metrics: Metrics | None = None, *, logger: ILogger) -> None:
        """Инициализирует сервис записи метрик.

        Args:
            metrics: Экземпляр Metrics для записи метрик (ОБЯЗАТЕЛЬНЫЙ).
            logger: Экземпляр логгера для использования в сервисе.

        Raises:
            ValueError: Если metrics равен None.
        """
        if metrics is None:
            raise ValueError("metrics не может быть None. Передайте экземпляр Metrics через Dependency Injection.")
        super().__init__(logger)
        self._metrics = metrics

    async def increment_generation_success(self, connection: asyncpg.Connection | None = None) -> None:
        """Увеличивает счётчик успешных генераций изображений."""
        try:
            await self._metrics.increment_generation_success(connection=connection)
            self.logger.debug(
                "Записана метрика: increment_generation_success",
                event="metric_recorded",
                status="success",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_generation_success: {e}")

    async def increment_generation_failed(self, connection: asyncpg.Connection | None = None) -> None:
        """Увеличивает счётчик неудачных генераций изображений."""
        try:
            await self._metrics.increment_generation_failed(connection=connection)
            self.logger.debug(
                "Записана метрика: increment_generation_failed",
                event="metric_recorded",
                status="failed",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_generation_failed: {e}")

    async def increment_cache_hit(self) -> None:
        """Увеличивает счётчик попаданий в кэш."""
        try:
            # В текущей реализации Metrics нет метода increment_cache_hit,
            # но мы можем использовать record_metric для записи события
            from infra.metrics.metrics import record_metric

            await record_metric(event_type="cache_hit", status="hit")
            self.logger.debug(
                "Записана метрика: increment_cache_hit",
                event="metric_recorded",
                status="cache_hit",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_cache_hit: {e}")

    async def increment_dispatch_success(self, connection: asyncpg.Connection | None = None) -> None:
        """Увеличивает счётчик успешных отправок сообщений."""
        try:
            await self._metrics.increment_dispatch_success(connection=connection)
            self.logger.debug(
                "Записана метрика: increment_dispatch_success",
                event="metric_recorded",
                status="success",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_dispatch_success: {e}")

    async def increment_dispatch_failed(self, connection: asyncpg.Connection | None = None) -> None:
        """Увеличивает счётчик неудачных отправок сообщений."""
        try:
            await self._metrics.increment_dispatch_failed(connection=connection)
            self.logger.debug(
                "Записана метрика: increment_dispatch_failed",
                event="metric_recorded",
                status="failed",
            )
        except Exception as e:
            self.logger.warning(f"Ошибка при записи метрики increment_dispatch_failed: {e}")

    async def record_circuit_breaker_trip(self) -> None:
        """Увеличивает счётчик срабатываний circuit breaker."""
        try:
            await self._metrics.increment_circuit_breaker_trip()
            self.logger.debug(
                "Записана метрика: record_circuit_breaker_trip",
                event="metric_recorded",
                status="circuit_breaker_trip",
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
