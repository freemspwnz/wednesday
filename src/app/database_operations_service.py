"""Сервис для выполнения групповых операций БД в транзакциях."""

from __future__ import annotations

from collections.abc import Callable

from shared.base.base_service import BaseService
from shared.protocols import IDatabaseUnitOfWork, IDispatchRegistry, IMetrics, IUsageTracker


class DatabaseOperationsService(BaseService):
    """Сервис для выполнения групповых операций БД в транзакциях.

    Инкапсулирует логику выполнения связанных операций БД (например,
    регистрация отправки, инкремент счётчика, обновление метрик) в одной транзакции.
    """

    def __init__(
        self,
        dispatch_registry: IDispatchRegistry,
        usage_tracker: IUsageTracker,
        metrics: IMetrics | None = None,
        unit_of_work_factory: Callable[[], IDatabaseUnitOfWork] | None = None,
    ) -> None:
        """Инициализирует сервис операций БД.

        Args:
            dispatch_registry: Реестр отправок.
            usage_tracker: Трекер использования.
            metrics: Сервис метрик (опционально).
            unit_of_work_factory: Фабрика для создания экземпляров Unit of Work.
        """
        super().__init__()
        self._dispatch_registry = dispatch_registry
        self._usage_tracker = usage_tracker
        self._metrics = metrics
        self._unit_of_work_factory = unit_of_work_factory

    async def record_dispatch_success(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
    ) -> None:
        """Регистрирует успешную отправку в транзакции.

        Выполняет в одной транзакции:
        - Отмечает отправку в dispatch_registry
        - Инкрементирует счётчик использования
        - Обновляет метрики успешных отправок

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: ID чата, в который была отправка.

        Raises:
            Exception: При ошибке выполнения операций (транзакция откатывается).
        """
        if self._unit_of_work_factory is None:
            # Fallback для обратной совместимости (breaking change - будет удалено)
            from infra.database.database_unit_of_work import DatabaseUnitOfWork
            from infra.database.postgres_client import get_postgres_pool

            def create_uow() -> IDatabaseUnitOfWork:
                return DatabaseUnitOfWork(pool=get_postgres_pool())

            uow: IDatabaseUnitOfWork = create_uow()
        else:
            uow = self._unit_of_work_factory()

        async with uow:
            connection = uow.connection

            try:
                # 1. Отмечаем в реестре
                await self._dispatch_registry.mark_dispatched(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    chat_id=chat_id,
                    connection=connection,
                )

                # 2. Инкрементируем счётчик
                await self._usage_tracker.increment(1, connection=connection)

                # 3. Обновляем метрики (если доступны)
                if self._metrics:
                    await self._metrics.increment_dispatch_success(connection=connection)

                # Коммит происходит автоматически при выходе из async with

            except Exception as e:
                # Откат происходит автоматически при исключении
                self.logger.error(
                    f"Ошибка при регистрации успешной отправки: {e}",
                    exc_info=True,
                )
                raise

    async def record_dispatch_failure(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
    ) -> None:
        """Регистрирует неуспешную отправку.

        Обновляет только метрики (dispatch_registry и usage не изменяются).

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: ID чата, в который была попытка отправки.
        """
        if not self._metrics:
            return

        try:
            # Метрики не критичны, можно выполнить без транзакции
            # или в отдельной транзакции
            await self._metrics.increment_dispatch_failed()
        except Exception as e:
            # Метрики не критичны, только логируем
            self.logger.warning(f"Ошибка при обновлении метрик неуспешной отправки: {e}")
