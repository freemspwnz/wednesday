"""
Простые сервисы для ограничения частоты запросов на базе Redis.

Основные компоненты:
- RateLimiter — фиксированное окно (fixed window) на основе INCR + EXPIRE.
  Подходит для простых сценариев, когда не требуется "плавное" скольжение окна.

Общие принципы:
- Все операции выполняются атомарно за счёт команд Redis (INCR/EXPIRE).

Примечание: CircuitBreaker перенесён в отдельный модуль
services/infrastructure/rate_limiting/circuit_breaker.py.
"""

from __future__ import annotations

import redis.asyncio as redis

from shared.base.redis_backend_service import RedisBackendService


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
        redis_client: redis.Redis,
        *,
        prefix: str = "rate:",
        window: int = 60,
        limit: int = 100,
    ) -> None:
        """Инициализирует лимитер с фиксированным окном.

        Args:
            redis_client: Экземпляр Redis клиента.
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

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        full_key = self._key(key)
        count = int(await self._redis.incr(full_key))
        if count == 1:
            await self._redis.expire(full_key, self.window)
        return count <= self.limit

    async def reset(self, key: str) -> None:
        """Сбрасывает счётчик по ключу.

        Удаляет ключ из Redis, сбрасывая счётчик запросов для указанного ключа.

        Args:
            key: Ключ, для которого нужно сбросить счётчик.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        full_key = self._key(key)
        await self._redis.delete(full_key)
