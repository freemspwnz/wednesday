"""Application service для расчета стратегии retry.

Инкапсулирует логику расчета времени ожидания и нормализации параметров retry,
соблюдая границы слоёв и централизуя бизнес-правила retry-стратегии.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.constants import (
    MAX_RETRIES_LIMIT,
    RETRY_DELAY_DEFAULT,
)
from shared.protocols.infrastructure import ILogger


class RetryStrategyService(BaseService):
    """Сервис для расчета стратегии retry.

    Инкапсулирует логику расчета времени ожидания и нормализации параметров retry,
    централизуя бизнес-правила retry-стратегии.
    """

    def __init__(
        self,
        *,
        base_delay: float = RETRY_DELAY_DEFAULT,
        max_retries_limit: int = MAX_RETRIES_LIMIT,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис retry-стратегии.

        Args:
            base_delay: Базовая задержка между попытками в секундах.
            max_retries_limit: Максимальное количество попыток для защиты от утечек памяти.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._base_delay = base_delay
        self._max_retries_limit = max_retries_limit

    def calculate_wait_time(self, attempt: int) -> float:
        """Рассчитывает время ожидания перед следующей попыткой.

        Использует линейную стратегию: wait_time = base_delay * attempt.

        Args:
            attempt: Номер текущей попытки (начинается с 1).

        Returns:
            Время ожидания в секундах перед следующей попыткой.
        """
        return self._base_delay * attempt

    def normalize_max_retries(self, max_retries: int) -> int:
        """Нормализует значение max_retries для защиты от утечек памяти.

        Обеспечивает, что max_retries находится в допустимых пределах:
        - Минимум: 1
        - Максимум: max_retries_limit

        Args:
            max_retries: Исходное значение max_retries.

        Returns:
            Нормализованное значение max_retries.
        """
        max_retries = max(max_retries, 1)
        if max_retries > self._max_retries_limit:
            self.logger.warning(
                f"max_retries={max_retries} слишком большой, ограничиваем до {self._max_retries_limit}",
            )
            return self._max_retries_limit
        return max_retries
