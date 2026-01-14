"""Билдеры для rate‑limiters и circuit breaker.

Модуль ограничивается инфраструктурным уровнем и не знает о Telegram‑боте.
"""

from __future__ import annotations

from infra.rate_limiting.circuit_breaker import CircuitBreakerService
from infra.rate_limiting.rate_limiter import RateLimiter
from infra.redis.redis_client import RedisClient
from shared.config import AppSettings, Config
from shared.protocols.infrastructure import ICircuitBreaker, IRateLimiter


def build_circuit_breaker(
    *,
    config: Config,
    redis_client: RedisClient,
) -> ICircuitBreaker:
    """Создаёт circuit breaker для защиты Kandinsky API."""
    cb_config = config.circuit_breaker
    return CircuitBreakerService(
        redis_client=redis_client,
        key="cb:kandinsky_api",
        threshold=cb_config.threshold,
        window=cb_config.window,
        cooldown=cb_config.cooldown,
    )


def build_frog_global_rate_limiter(
    *,
    app_settings: AppSettings,
    redis_client: RedisClient,
) -> IRateLimiter:
    """Глобальный rate limiter для команды /frog."""
    return RateLimiter(
        redis_client=redis_client,
        prefix="frog:global:",
        window=app_settings.frog_rate_limit_window_seconds,
        limit=app_settings.frog_rate_limit_max_requests,
    )


def build_frog_user_rate_limiter(
    *,
    app_settings: AppSettings,
    redis_client: RedisClient,
) -> IRateLimiter:
    """Пользовательский rate limiter для команды /frog."""
    seconds_per_minute = 60
    return RateLimiter(
        redis_client=redis_client,
        prefix="frog:user:",
        window=app_settings.frog_rate_limit_minutes * seconds_per_minute,
        limit=1,
    )


def build_telegram_api_rate_limiter(
    *,
    redis_client: RedisClient,
) -> IRateLimiter:
    """Rate limiter для Telegram API."""
    from app.telegram_api_rate_limiter_service import (
        TELEGRAM_API_MAX_REQUESTS_PER_SECOND,
        TELEGRAM_API_WINDOW_SECONDS,
    )

    return RateLimiter(
        redis_client=redis_client,
        prefix="telegram_api:",
        window=TELEGRAM_API_WINDOW_SECONDS,
        limit=TELEGRAM_API_MAX_REQUESTS_PER_SECOND,
    )
