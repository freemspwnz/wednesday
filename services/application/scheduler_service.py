"""Application service для оркестрации планирования задач.

Координирует работу TaskScheduler для автоматического выполнения задач по расписанию.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from services.base.base_service import BaseService
from services.scheduler import TaskScheduler


class SchedulerService(BaseService):
    """Application service для оркестрации планирования задач.

    Координирует работу TaskScheduler для автоматического выполнения задач.
    Использует TaskScheduler как инфраструктурный компонент.
    """

    def __init__(
        self,
        scheduler: TaskScheduler,
    ) -> None:
        """Инициализирует сервис оркестрации планирования.

        Args:
            scheduler: Экземпляр TaskScheduler для использования.
        """
        super().__init__()
        self._scheduler = scheduler

    def schedule_wednesday_task(self, task_func: Callable[[str | None], Awaitable[None]]) -> None:
        """Планирует задачу на выполнение каждую среду.

        Args:
            task_func: Асинхронная функция для выполнения.
        """
        self.logger.info("Планирую задачу на среду через SchedulerService")
        self._scheduler.schedule_wednesday_task(task_func)
        self.logger.info("Задача на среду успешно запланирована")

    def schedule_daily_task(self, task_func: Callable[[], Awaitable[None]], time_str: str) -> None:
        """Планирует ежедневную задачу.

        Args:
            task_func: Асинхронная функция для выполнения.
            time_str: Время выполнения в формате "HH:MM".
        """
        self.logger.info(f"Планирую ежедневную задачу в {time_str} через SchedulerService")
        self._scheduler.schedule_daily_task(task_func, time_str)
        self.logger.info("Ежедневная задача успешно запланирована")

    def schedule_interval_task(self, task_func: Callable[[], Awaitable[None]], interval_minutes: int) -> None:
        """Планирует интервальную задачу.

        Args:
            task_func: Асинхронная функция для выполнения.
            interval_minutes: Интервал между выполнениями в минутах.
        """
        self.logger.info(f"Планирую интервальную задачу с интервалом {interval_minutes} минут через SchedulerService")
        self._scheduler.schedule_interval_task(task_func, interval_minutes)
        self.logger.info("Интервальная задача успешно запланирована")

    async def start(self) -> None:
        """Запускает планировщик задач.

        Запускает TaskScheduler для выполнения запланированных задач.
        """
        self.logger.info("Запускаю планировщик задач через SchedulerService")
        await self._scheduler.start()

    def stop(self) -> None:
        """Останавливает планировщик задач.

        Останавливает TaskScheduler и завершает выполнение задач.
        """
        self.logger.info("Останавливаю планировщик задач через SchedulerService")
        self._scheduler.stop()

    def get_next_run(self) -> datetime | None:
        """Возвращает время следующего запланированного выполнения.

        Returns:
            Время следующего выполнения или None, если нет запланированных задач.
        """
        return self._scheduler.get_next_run()

    def clear_all_jobs(self) -> None:
        """Очищает все запланированные задачи."""
        self.logger.info("Очищаю все запланированные задачи через SchedulerService")
        self._scheduler.clear_all_jobs()

    def get_jobs_count(self) -> int:
        """Возвращает количество запланированных задач.

        Returns:
            Количество активных задач.
        """
        return self._scheduler.get_jobs_count()
