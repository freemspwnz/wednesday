"""Сервис для выполнения групповых операций БД в транзакциях."""

from __future__ import annotations

import asyncpg

from shared.base.base_service import BaseService
from shared.base.exceptions import RepoError, ServiceError, UnexpectedAppError
from shared.protocols import (
    IDispatchRegistry,
    ILogger,
    IMetrics,
    IUnitOfWorkFactory,
    IUsageTracker,
)


class DatabaseOperationsService(BaseService):
    """Сервис для выполнения групповых операций БД в транзакциях.

    Инкапсулирует логику выполнения связанных операций БД (например,
    регистрация отправки, инкремент счётчика, обновление метрик) в одной транзакции.
    """

    def __init__(
        self,
        dispatch_registry: IDispatchRegistry,
        usage_tracker: IUsageTracker,
        unit_of_work_factory: IUnitOfWorkFactory,
        metrics: IMetrics | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис операций БД.

        Args:
            dispatch_registry: Реестр отправок.
            usage_tracker: Трекер использования.
            metrics: Сервис метрик (опционально).
            unit_of_work_factory: Фабрика для создания экземпляров Unit of Work (обязательная зависимость).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
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
            RepoError: При ошибке выполнения операций (транзакция откатывается).
        """
        uow = self._unit_of_work_factory()

        async with uow:
            # Явная типизация connection для ясности типа
            connection: asyncpg.Connection = uow.connection

            try:
                # 1. Отмечаем в реестре
                await self._dispatch_registry.mark_dispatched(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    chat_id=chat_id,
                    connection=connection,
                )

                # 2. Инкрементируем счётчик
                await self._usage_tracker.increment(connection=connection, count=1)

                # 3. Обновляем метрики (если доступны)
                if self._metrics:
                    await self._metrics.increment_dispatch_success(connection=connection)

                # Коммит происходит автоматически при выходе из async with

            except RepoError as e:
                # Откат происходит автоматически при исключении
                # Логируем безопасно, чтобы не скрыть оригинальную ошибку
                self._safe_log_error(
                    f"Ошибка при регистрации успешной отправки: {e}",
                    e,
                    context={
                        "event": "repo_error",
                        "slot_date": slot_date,
                        "slot_time": slot_time,
                        "chat_id": chat_id,
                    },
                )
                # Пробрасываем оригинальную ошибку независимо от результата логирования
                raise

    async def reserve_and_finalize_dispatch(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
    ) -> bool:
        """Бронирует отправку и выполняет финализацию (usage, metrics).

        Выполняет в одной транзакции:
        1. Попытка бронирования отправки (атомарный захват)
        2. Если бронь получена - финализация (increment usage, metrics)
        3. Если бронь не получена - ничего не делаем

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: ID чата, для которого бронируется отправка.

        Returns:
            True если бронь получена и финализация выполнена,
            False если отправка уже забронирована/выполнена другим процессом.

        Raises:
            RepoError: При ошибке выполнения операций (транзакция откатывается).
        """
        uow = self._unit_of_work_factory()

        async with uow:
            # Явная типизация connection для ясности типа
            connection: asyncpg.Connection = uow.connection

            try:
                # 1. Пытаемся забронировать (атомарный захват)
                reservation_success = await self._dispatch_registry.try_reserve_dispatch(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    chat_id=chat_id,
                    connection=connection,
                )

                if not reservation_success:
                    # Бронь не получена - уже забронировано другим процессом
                    # Транзакция откатится автоматически (ничего не было изменено)
                    return False

                # 2. Бронь получена - финализируем (increment usage, metrics)
                await self._usage_tracker.increment(connection=connection, count=1)

                if self._metrics:
                    await self._metrics.increment_dispatch_success(connection=connection)

                # Коммит происходит автоматически при выходе из async with
                return True

            except RepoError as e:
                # Откат происходит автоматически при исключении
                self._safe_log_error(
                    f"Ошибка при бронировании/финализации отправки: {e}",
                    e,
                    context={
                        "event": "dispatch_reservation_error",
                        "slot_date": slot_date,
                        "slot_time": slot_time,
                        "chat_id": chat_id,
                    },
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
            await self._metrics.increment_dispatch_failed_with_pool()
        except ServiceError as e:
            # Метрики не критичны, только логируем
            self.logger.warning(
                f"Ошибка при обновлении метрик неуспешной отправки: {e}",
                event="metrics_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
            )
        except BaseException as e:
            # Неожиданные ошибки (метрики не критичны, только логируем)
            # Системные ошибки обрабатываются внутри handle_unexpected_error
            self.handle_unexpected_error(
                e,
                UnexpectedAppError,
                message=f"Неожиданная ошибка при обновлении метрик неуспешной отправки: {e}",
                context={"event": "unexpected_error"},
            )
