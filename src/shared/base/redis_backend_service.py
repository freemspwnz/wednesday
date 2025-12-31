"""Базовый класс для сервисов, работающих с Redis."""

from __future__ import annotations

import redis.asyncio as redis

from shared.base.base_service import BaseService
from shared.protocols.infrastructure import ILogger


class RedisBackendService(BaseService):
    """Базовый класс для сервисов, работающих с Redis.

    Предоставляет:
    - Унифицированную работу с префиксами ключей
    - Типизированный доступ к Redis клиенту
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        prefix: str = "",
        logger: ILogger | None = None,
    ) -> None:
        """Инициализирует Redis-сервис.

        Args:
            redis_client: Экземпляр Redis клиента.
            prefix: Префикс для всех ключей этого сервиса (по умолчанию "").
            logger: Экземпляр логгера для использования в сервисе. Если None, создается новый.
        """
        from infra.logging.logger import get_logger

        if logger is None:
            logger = get_logger(self.__class__.__name__)
        super().__init__(logger)
        self._redis: redis.Redis = redis_client
        self._prefix = prefix

    def _key(self, key: str) -> str:
        """Формирует полный ключ с префиксом.

        Args:
            key: Базовый ключ без префикса.

        Returns:
            Полный ключ с префиксом сервиса.
        """
        return f"{self._prefix}{key}"
