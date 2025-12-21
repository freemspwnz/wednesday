"""
Простые сервисы для ограничения частоты запросов на базе Redis.

Основные компоненты:
- RateLimiter — фиксированное окно (fixed window) на основе INCR + EXPIRE.
  Подходит для простых сценариев, когда не требуется "плавное" скольжение окна.

Общие принципы:
- Все операции выполняются атомарно за счёт команд Redis (INCR/EXPIRE).
- При недоступности Redis сервисы переходят в fail‑open режим и работают в памяти.
  Это сделано сознательно, чтобы инфраструктурные проблемы не блокировали пользователей.

Примечание: CircuitBreaker перенесён в отдельный модуль
services/infrastructure/rate_limiting/circuit_breaker.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis.asyncio as redis

from infra.redis.redis_client import _InMemoryRedis
from shared.base.redis_backend_service import RedisBackendService

if TYPE_CHECKING:
    RedisBackend = redis.Redis | _InMemoryRedis
else:
    RedisBackend = redis.Redis | _InMemoryRedis


class RateLimiter(RedisBackendService):
    """
    Простейший лимитер типа "фиксированное окно".

    Алгоритм:
    - Ключ = f"{prefix}{key}".
    - `count = INCR(key)`; если count == 1 — сразу выставляем EXPIRE на `window` секунд.
    - Разрешаем запрос, если `count <= limit`.

    Trade‑off:
    - Fixed window проще и дешевле, но создаёт "ступеньки" на границе окна.
      Для более плавного поведения можно заменить на sliding window или token bucket (Lua).
    """

    def __init__(
        self,
        redis_client: RedisBackend,
        *,
        prefix: str = "rate:",
        window: int = 60,
        limit: int = 100,
    ) -> None:
        """Инициализирует лимитер с фиксированным окном.

        Args:
            redis_client: Экземпляр Redis или совместимого клиента.
            prefix: Префикс для всех ключей лимитера (по умолчанию "rate:").
            window: Размер временного окна в секундах (по умолчанию 60).
            limit: Максимальное количество запросов в окне (по умолчанию 100).
        """
        super().__init__(redis_client=redis_client, prefix=prefix)
        self.window = window
        self.limit = limit

    async def is_allowed(self, key: str) -> bool:
        """Возвращает True, если запрос разрешён, и инкрементирует счётчик.

        Проверяет, не превышен ли лимит запросов для указанного ключа в текущем
        временном окне. Автоматически инкрементирует счётчик запросов.

        Args:
            key: Уникальный ключ для идентификации источника запросов.

        Returns:
            True если запрос разрешён (счётчик не превышает лимит), False в противном случае.

        Note:
            При недоступности Redis переходит в in-memory режим (fail-open), чтобы
            не блокировать пользователей. Лимиты в этом режиме действуют только в
            рамках текущего процесса.
        """
        full_key = self._key(key)

        async def _incr_operation(backend: RedisBackend) -> int:
            count = await backend.incr(full_key)
            if count == 1:
                await backend.expire(full_key, self.window)
            return count

        count = await self._execute_with_fallback(_incr_operation)
        return count <= self.limit

    async def reset(self, key: str) -> None:
        """Сбрасывает счётчик по ключу (в Redis и fallback).

        Удаляет ключ из Redis и из in-memory fallback, сбрасывая счётчик запросов
        для указанного ключа.

        Args:
            key: Ключ, для которого нужно сбросить счётчик.

        Note:
            При ошибке Redis сброс выполняется только в fallback кэше.
        """
        full_key = self._key(key)

        async def _delete_operation(backend: RedisBackend) -> None:
            await backend.delete(full_key)

        await self._execute_with_fallback(_delete_operation)
