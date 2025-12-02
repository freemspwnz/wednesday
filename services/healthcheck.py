"""
HTTP‑эндпоинт healthcheck для бота.

Реализован как небольшое FastAPI‑приложение, которое:
- проверяет доступность Redis (включая реальный ping, если доступен);
- проверяет доступность Postgres (простым запросом SELECT 1);
- проверяет наличие и доступность основной бизнес‑очереди Redis Stream
  `metrics:events` через XINFO STREAM;
- возвращает агрегированный JSON‑статус и HTTP‑код 200, если все
  критичные зависимости в состоянии "up", иначе 503.

Эндпоинт предназначен для:
- Docker HEALTHCHECK;
- внешних систем мониторинга/оркестрации (k8s liveness/readiness probes);
- быстрых ручных проверок состояния сервиса.
"""

from __future__ import annotations

import time
from typing import Any

import asyncpg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from utils.logger import get_logger, log_event
from utils.postgres_client import get_postgres_pool
from utils.redis_client import get_redis, redis_available

logger = get_logger(__name__)

# Экспортируемое FastAPI‑приложение. Uvicorn использует его для запуска
# HTTP‑сервера внутри основного процесса бота.
app = FastAPI(title="Wednesday Frog Bot Healthcheck")


async def _check_redis() -> dict[str, Any]:
    """
    Выполняет проверку доступности Redis.

    Возвращает структуру:
        {
            "status": "up" | "down",
            "using_fallback": bool,
            "latency_ms": float | None,
            "details": str | None,
        }
    """
    started = time.monotonic()
    using_real = redis_available()
    client = get_redis()

    if not using_real:
        # В приложении в этом случае используется in‑memory fallback.
        # Для healthcheck считаем Redis критичным, поэтому статус "down".
        return {
            "status": "down",
            "using_fallback": True,
            "latency_ms": None,
            "details": "Redis недоступен, используется in‑memory fallback",
        }

    # В тестах (и потенциально в других окружениях) get_redis может быть
    # замокан на класс вместо инстанса. В этом случае создаём экземпляр.
    if isinstance(client, type):
        client = client()

    try:
        ping = getattr(client, "ping", None)
        if callable(ping):
            await ping()
        latency_ms = (time.monotonic() - started) * 1000.0
        return {
            "status": "up",
            "using_fallback": False,
            "latency_ms": latency_ms,
            "details": None,
        }
    except RedisError as exc:
        latency_ms = (time.monotonic() - started) * 1000.0
        logger.error(f"Ошибка при проверке Redis в healthcheck: {exc!s}", exc_info=True)
        return {
            "status": "down",
            "using_fallback": False,
            "latency_ms": latency_ms,
            "details": str(exc),
        }
    except Exception as exc:  # pragma: no cover - защитный фоллбек
        latency_ms = (time.monotonic() - started) * 1000.0
        logger.error(f"Неожиданная ошибка при проверке Redis в healthcheck: {exc!s}", exc_info=True)
        return {
            "status": "down",
            "using_fallback": False,
            "latency_ms": latency_ms,
            "details": str(exc),
        }


async def _check_postgres() -> dict[str, Any]:
    """
    Выполняет проверку доступности Postgres.

    Возвращает структуру:
        {
            "status": "up" | "down",
            "latency_ms": float | None,
            "details": str | None,
        }
    """
    started = time.monotonic()
    try:
        pool = get_postgres_pool()
    except RuntimeError as exc:
        # Пул не инициализирован — для healthcheck это значит, что БД недоступна.
        return {
            "status": "down",
            "latency_ms": None,
            "details": str(exc),
        }

    # В тестах get_postgres_pool может быть подменён на класс‑заглушку.
    # В этом случае создаём экземпляр перед использованием.
    if isinstance(pool, type):
        pool = pool()

    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1;")
        latency_ms = (time.monotonic() - started) * 1000.0
        return {
            "status": "up",
            "latency_ms": latency_ms,
            "details": None,
        }
    except asyncpg.PostgresError as exc:
        latency_ms = (time.monotonic() - started) * 1000.0
        logger.error(f"Ошибка Postgres в healthcheck: {exc!s}", exc_info=True)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "details": str(exc),
        }
    except Exception as exc:  # pragma: no cover - защитный фоллбек
        latency_ms = (time.monotonic() - started) * 1000.0
        logger.error(f"Неожиданная ошибка при проверке Postgres в healthcheck: {exc!s}", exc_info=True)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "details": str(exc),
        }


async def _check_metrics_stream() -> dict[str, Any]:
    """
    Проверяет доступность основной бизнес‑очереди Redis Stream `metrics:events`.

    Возвращает структуру:
        {
            "status": "up" | "down",
            "latency_ms": float | None,
            "details": str | None,
        }

    Логика:
    - если Redis недоступен — очередь считаем "down";
    - если команда XINFO STREAM завершилась успешно — "up";
    - если ключ отсутствует (ERR no such key) — считаем "down", так как
      это важная очередь бизнес‑метрик.
    """
    started = time.monotonic()
    using_real = redis_available()
    client = get_redis()

    # Если Redis недоступен (in‑memory fallback), очередь считаем down.
    if not using_real:
        return {
            "status": "down",
            "latency_ms": None,
            "details": "Redis недоступен или используется in‑memory fallback",
        }

    # Аналогично _check_redis, учитываем возможность подмены на класс в тестах.
    if isinstance(client, type):
        client = client()

    try:
        xinfo = getattr(client, "xinfo_stream", None)
        if callable(xinfo):
            await xinfo("metrics:events")
        latency_ms = (time.monotonic() - started) * 1000.0
        return {
            "status": "up",
            "latency_ms": latency_ms,
            "details": None,
        }
    except RedisError as exc:
        latency_ms = (time.monotonic() - started) * 1000.0
        logger.error(f"Ошибка XINFO STREAM metrics:events в healthcheck: {exc!s}", exc_info=True)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "details": str(exc),
        }
    except Exception as exc:  # pragma: no cover - защитный фоллбек
        latency_ms = (time.monotonic() - started) * 1000.0
        logger.error(
            f"Неожиданная ошибка при проверке очереди metrics:events в healthcheck: {exc!s}",
            exc_info=True,
        )
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "details": str(exc),
        }


async def _build_health_payload() -> dict[str, Any]:
    """
    Выполняет все проверки и формирует итоговый JSON‑ответ healthcheck.

    Структура ответа:
        {
            "status": "up" | "down",
            "redis": {...},
            "postgres": {...},
            "queues": {
                "metrics_events": {...}
            },
            "latency_ms": float
        }
    """
    started = time.monotonic()
    redis_status = await _check_redis()
    postgres_status = await _check_postgres()
    metrics_stream_status = await _check_metrics_stream()

    # Все три зависимости считаются критичными для статуса "up":
    # - Redis (в том числе для лимитеров, кэшей и circuit‑breaker);
    # - Postgres (персистентное хранилище);
    # - основная очередь метрик metrics:events.
    all_ok = (
        redis_status.get("status") == "up"
        and postgres_status.get("status") == "up"
        and metrics_stream_status.get("status") == "up"
    )
    overall_status = "up" if all_ok else "down"

    total_latency_ms = (time.monotonic() - started) * 1000.0

    payload: dict[str, Any] = {
        "status": overall_status,
        "redis": redis_status,
        "postgres": postgres_status,
        "queues": {
            "metrics_events": metrics_stream_status,
        },
        "latency_ms": total_latency_ms,
    }

    # При любом неблагополучном состоянии логируем структурированное событие.
    if not all_ok:
        log_event(
            event="healthcheck_failed",
            status="error",
            latency_ms=total_latency_ms,
            extra={
                "redis_status": redis_status.get("status"),
                "postgres_status": postgres_status.get("status"),
                "metrics_events_status": metrics_stream_status.get("status"),
            },
            level="error",
            message="Healthcheck зависимости бота не в состоянии up",
        )

    return payload


@app.get("/health")
async def health() -> JSONResponse:
    """
    Основной HTTP‑эндпоинт healthcheck.

    Возвращает:
    - HTTP 200 и status="up", если все критические зависимости доступны;
    - HTTP 503 и status="down" в противном случае.
    """
    payload = await _build_health_payload()
    http_status = 200 if payload.get("status") == "up" else 503
    return JSONResponse(content=payload, status_code=http_status)
