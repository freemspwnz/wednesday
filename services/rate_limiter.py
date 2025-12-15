"""
Простые сервисы для ограничения частоты запросов и circuit‑breaker на базе Redis.

Основные компоненты:
- RateLimiter — фиксированное окно (fixed window) на основе INCR + EXPIRE.
  Подходит для простых сценариев, когда не требуется "плавное" скольжение окна.
- CircuitBreaker — счётчик неудач с окном жизни и флагом "открыт/закрыт".

Общие принципы:
- Все операции выполняются атомарно за счёт команд Redis (INCR/EXPIRE/HINCRBY/HSET).
- При недоступности Redis сервисы переходят в fail‑open режим и работают в памяти.
  Это сделано сознательно, чтобы инфраструктурные проблемы не блокировали пользователей.
"""

from __future__ import annotations

import logging
import time
from typing import TypeAlias

import redis.asyncio as redis
from redis.exceptions import RedisError

from utils.redis_client import _InMemoryRedis, get_redis

logger = logging.getLogger(__name__)


RedisBackend: TypeAlias = redis.Redis | _InMemoryRedis


class RateLimiter:
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
        redis_client: RedisBackend | None = None,
        *,
        prefix: str = "rate:",
        window: int = 60,
        limit: int = 100,
    ) -> None:
        """Инициализирует лимитер с фиксированным окном.

        Args:
            redis_client: Экземпляр Redis или совместимого клиента. Если None,
                используется глобальный клиент через get_redis().
            prefix: Префикс для всех ключей лимитера (по умолчанию "rate:").
            window: Размер временного окна в секундах (по умолчанию 60).
            limit: Максимальное количество запросов в окне (по умолчанию 100).
        """
        backend = redis_client or get_redis()
        self._redis: RedisBackend = backend
        self._fallback: _InMemoryRedis = _InMemoryRedis()
        self.prefix = prefix
        self.window = window
        self.limit = limit

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

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
        try:
            count = await self._redis.incr(full_key)
            if count == 1:
                await self._redis.expire(full_key, self.window)
            return count <= self.limit
        except RedisError as exc:
            logger.warning(
                f"Redis error в RateLimiter.is_allowed ({full_key}) — fallback in‑memory, policy=fail‑open: {exc!s}",
            )
            # Локальный лимитер; пригоден только как деградационный режим.
            count = await self._fallback.incr(full_key)
            if count == 1:
                await self._fallback.expire(full_key, self.window)
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
        try:
            await self._redis.delete(full_key)
        except RedisError as exc:
            logger.warning(
                f"Redis error в RateLimiter.reset ({full_key}) — очищаем только fallback: {exc!s}",
            )
        await self._fallback.delete(full_key)


class CircuitBreaker:
    """
    Простой circuit‑breaker на Redis.

    Модель:
    - Храним hash по ключу: fields: `failures`, `last_failed_at`.
    - Каждая ошибка вызывает HINCRBY(failures) и HSET(last_failed_at=ts), EXPIRE(key, window).
    - Circuit считается "открытым", если failures >= threshold и с момента `last_failed_at`
      прошло меньше `cooldown` секунд.
    """

    def __init__(
        self,
        redis_client: RedisBackend | None = None,
        *,
        key: str = "cb:default",
        threshold: int = 5,
        window: int = 300,
        cooldown: int | None = None,
    ) -> None:
        """Инициализирует circuit breaker.

        Args:
            redis_client: Экземпляр Redis или совместимого клиента. Если None,
                используется глобальный клиент через get_redis().
            key: Логический ключ ресурса (например, 'kandinsky_api').
            threshold: Количество ошибок до открытия circuit-breaker (по умолчанию 5).
            window: Окно жизни счётчика ошибок в секундах через EXPIRE (по умолчанию 300).
            cooldown: Минимальный интервал после последней ошибки в секундах, в течение
                которого circuit считается открытым. По умолчанию равен window.
        """
        backend = redis_client or get_redis()
        self._redis: RedisBackend = backend
        self._fallback: _InMemoryRedis = _InMemoryRedis()
        self.key = key
        self.threshold = threshold
        self.window = window
        self.cooldown = cooldown if cooldown is not None else window

    @staticmethod
    def _now() -> float:
        return time.time()

    async def is_open(self) -> bool:
        """Возвращает True, если circuit-breaker "открыт".

        Проверяет состояние circuit-breaker: открыт ли он (заблокирован) или закрыт
        (разрешены запросы). Circuit считается открытым, если количество ошибок
        превышает threshold и с момента последней ошибки прошло меньше cooldown секунд.

        Returns:
            True если circuit-breaker открыт и запросы к защищаемому ресурсу блокируются,
            False если circuit-breaker закрыт и запросы разрешены.

        Note:
            При недоступности Redis проверка выполняется в in-memory fallback.
        """
        try:
            data = await self._redis.hgetall(self.key)  # type: ignore[misc]
        except RedisError as exc:
            logger.warning(
                f"Redis error в CircuitBreaker.is_open ({self.key}) — используем fallback in‑memory: {exc!s}",
            )
            data = await self._fallback.hgetall(self.key)

        if not data:
            return False

        try:
            failures = int(data.get("failures", "0"))
            last_failed_at = float(data.get("last_failed_at", "0"))
        except (TypeError, ValueError):
            return False

        if failures < self.threshold:
            return False

        # Окно "покоя" после последней ошибки.
        since_last = self._now() - last_failed_at
        return since_last < self.cooldown

    async def record_failure(self) -> None:
        """Регистрирует неудачу и обновляет состояние circuit-breaker.

        Увеличивает счётчик ошибок и обновляет время последней ошибки. Если количество
        ошибок превышает threshold, circuit-breaker переходит в открытое состояние.

        Note:
            При недоступности Redis запись выполняется в in-memory fallback.
        """
        now_ts = self._now()
        mapping = {"last_failed_at": str(now_ts)}
        try:
            failures = await self._redis.hincrby(self.key, "failures", 1)  # type: ignore[misc]
            await self._redis.hset(self.key, mapping=mapping)  # type: ignore[misc]
            # Обновляем TTL окна.
            await self._redis.expire(self.key, self.window)
            logger.debug(
                f"CircuitBreaker {self.key}: failures={failures}, last_failed_at={now_ts}",
            )
        except RedisError as exc:
            logger.warning(
                f"Redis error в CircuitBreaker.record_failure ({self.key}) — используем fallback in‑memory: {exc!s}",
            )
            failures = await self._fallback.hincrby(self.key, "failures", 1)
            await self._fallback.hset(self.key, mapping=mapping)
            await self._fallback.expire(self.key, self.window)
            logger.debug(
                f"CircuitBreaker (fallback) {self.key}: failures={failures}, last_failed_at={now_ts}",
            )

    async def reset(self) -> None:
        """Полностью сбрасывает состояние circuit-breaker.

        Удаляет все данные о состоянии circuit-breaker из Redis и из in-memory fallback,
        сбрасывая счётчик ошибок и время последней ошибки.

        Note:
            При ошибке Redis сброс выполняется только в fallback кэше.
        """
        try:
            await self._redis.delete(self.key)
        except RedisError as exc:
            logger.warning(
                f"Redis error в CircuitBreaker.reset ({self.key}) — очищаем только fallback: {exc!s}",
            )
        await self._fallback.delete(self.key)
