"""Базовый класс для сервисов, работающих с Redis."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

import redis.asyncio as redis
from redis.exceptions import RedisError

from services.base.base_service import BaseService
from utils.redis_client import _InMemoryRedis, get_redis

if TYPE_CHECKING:
    pass

T = TypeVar("T")
RedisBackend = redis.Redis | _InMemoryRedis


class RedisBackendService(BaseService):
    """Базовый класс для сервисов, работающих с Redis.

    Предоставляет:
    - Автоматический fallback на in-memory Redis при ошибках
    - Унифицированную работу с префиксами ключей
    - Типизированный метод _execute_with_fallback для безопасных операций
    """

    def __init__(
        self,
        redis_client: RedisBackend | None = None,
        *,
        prefix: str = "",
    ) -> None:
        """Инициализирует Redis-сервис.

        Args:
            redis_client: Экземпляр Redis или совместимого клиента. Если None,
                используется глобальный клиент через get_redis().
            prefix: Префикс для всех ключей этого сервиса (по умолчанию "").
        """
        super().__init__()
        self._redis: RedisBackend = redis_client or get_redis()
        self._prefix = prefix
        self._fallback: _InMemoryRedis = _InMemoryRedis()

    def _key(self, key: str) -> str:
        """Формирует полный ключ с префиксом.

        Args:
            key: Базовый ключ без префикса.

        Returns:
            Полный ключ с префиксом сервиса.
        """
        return f"{self._prefix}{key}"

    async def _execute_with_fallback(
        self,
        operation: Callable[[RedisBackend], Awaitable[T]],
        *,
        log_on_fallback: bool = True,
    ) -> T:
        """Выполняет операцию Redis с автоматическим fallback на in-memory.

        Args:
            operation: Асинхронная функция, принимающая RedisBackend и возвращающая результат.
            log_on_fallback: Логировать ли переход на fallback (по умолчанию True).

        Returns:
            Результат операции (из Redis или fallback).

        Note:
            При ошибке Redis автоматически переходит на in-memory fallback.
            Логирование fallback-переходов выполняется через self.logger.
        """
        try:
            return await operation(self._redis)
        except RedisError as exc:
            if log_on_fallback:
                self.logger.warning(
                    f"Redis error in {self.__class__.__name__} — fallback to in-memory: {exc!s}",
                )
            return await operation(self._fallback)
