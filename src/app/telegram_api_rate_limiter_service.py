"""Application service для rate limiting вызовов Telegram API.

Инкапсулирует логику ограничения частоты запросов к Telegram API
с использованием инфраструктурного IRateLimiter и семафора для параллелизма.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

from shared.base.base_service import BaseService
from shared.config import AppSettings
from shared.protocols.infrastructure import ILogger, IRateLimiter

if TYPE_CHECKING:
    pass

T = TypeVar("T")

# Константы для Telegram API rate limits
# Telegram API: 30 сообщений в секунду на бота
TELEGRAM_API_MAX_REQUESTS_PER_SECOND = 30
TELEGRAM_API_WINDOW_SECONDS = 1
TELEGRAM_API_MAX_PARALLEL_REQUESTS = 10  # Консервативное ограничение параллелизма


class TelegramAPIRateLimiterService(BaseService):
    """Application service для проактивной защиты от rate limiting Telegram API.

    Обеспечивает два уровня защиты:
    - Rate limiting: ограничение частоты запросов через IRateLimiter
    - Parallelism limiting: ограничение параллельных запросов через семафор

    Telegram API лимиты:
    - 30 запросов в секунду на бота
    - Рекомендуется не более 10 параллельных запросов

    Используется для предотвращения превышения лимитов Telegram API до получения
    ошибок 429. Дополняет реактивную защиту через retry_on_connect_error.
    """

    def __init__(
        self,
        *,
        settings: AppSettings,
        api_limiter: IRateLimiter,
        logger: ILogger,
        max_parallel: int | None = None,
    ) -> None:
        """Инициализирует сервис rate limiting для Telegram API.

        Args:
            settings: Настройки приложения.
            api_limiter: Лимитер для ограничения частоты запросов к Telegram API.
            logger: Экземпляр логгера.
            max_parallel: Максимальное количество параллельных запросов.
                Если None, используется TELEGRAM_API_MAX_PARALLEL_REQUESTS.
        """
        super().__init__(logger)
        self._api_limiter = api_limiter
        self._max_parallel = max_parallel or TELEGRAM_API_MAX_PARALLEL_REQUESTS
        self._semaphore = asyncio.Semaphore(self._max_parallel)

    async def acquire(self) -> None:
        """Получает разрешение на выполнение запроса к Telegram API.

        Блокируется до получения разрешения (если достигнут лимит параллелизма).
        Также проверяет rate limit перед разрешением.

        Side Effects:
            - Блокирует выполнение если достигнут лимит параллелизма
            - Проверяет и инкрементирует rate limit счетчик
            - Логирует предупреждение при приближении к лимиту

        Note:
            Если rate limit превышен, логируется предупреждение, но запрос
            все равно разрешается. Это позволяет retry_on_connect_error
            обработать 429 ошибку с правильной задержкой (retry_after).
        """
        # Проверяем rate limit (проактивная защита)
        if not await self._api_limiter.is_allowed("telegram_api"):
            # Логируем, но не блокируем - пусть retry_on_connect_error обработает 429
            self.logger.warning(
                "Telegram API rate limit приближается к лимиту, "
                "но продолжаем выполнение (будет обработано при получении 429)",
            )

        # Ограничиваем параллелизм через семафор
        await self._semaphore.acquire()

    def release(self) -> None:
        """Освобождает разрешение на выполнение запроса.

        Должно вызываться в finally блоке после завершения запроса.
        """
        self._semaphore.release()

    async def execute_with_rate_limit(
        self,
        func: Callable[[], Awaitable[T]],
    ) -> T:
        """Выполняет функцию с защитой от rate limiting.

        Удобная обертка, которая автоматически управляет semaphore.

        Args:
            func: Асинхронная функция для выполнения.

        Returns:
            Результат выполнения функции.

        Side Effects:
            - Получает и освобождает семафор
            - Проверяет rate limit перед выполнением
        """
        await self.acquire()
        try:
            return await func()
        finally:
            self.release()
