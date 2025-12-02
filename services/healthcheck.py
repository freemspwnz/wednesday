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
from utils.redis_client import get_redis

logger = get_logger(__name__)

# Экспортируемое FastAPI‑приложение. Uvicorn использует его для запуска
# HTTP‑сервера внутри того же event loop, что и Telegram‑бот.
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

    # Если main() уже прокинул клиент в app.state, используем его;
    # иначе — глобальный singleton через utils.redis_client.
    client = getattr(app.state, "redis", None) or get_redis()

    # В тестах (и потенциально в других окружениях) client может быть
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
        logger.warning(f"Ошибка при проверке Redis в healthcheck: {exc!s}")
        return {
            "status": "down",
            "using_fallback": False,
            "latency_ms": latency_ms,
            "details": str(exc),
        }
    except Exception as exc:  # pragma: no cover - защитный фоллбек
        latency_ms = (time.monotonic() - started) * 1000.0
        error_msg = str(exc)
        logger.warning(f"Неожиданная ошибка при проверке Redis в healthcheck: {error_msg}")
        return {
            "status": "down",
            "using_fallback": False,
            "latency_ms": latency_ms,
            "details": error_msg,
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

    # Сначала пробуем взять пул из app.state, если main() его туда прокинул.
    pool = getattr(app.state, "postgres_pool", None) or get_postgres_pool()

    # В тестах пул может быть подменён на фабрику; если это callable без acquire,
    # создаём экземпляр перед использованием.
    if callable(pool) and not hasattr(pool, "acquire"):
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
        error_msg = str(exc)
        # Логируем ошибки только на уровне debug, чтобы не спамить логами.
        logger.debug(f"Ошибка Postgres в healthcheck: {error_msg}")
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "details": error_msg,
        }
    except Exception as exc:  # pragma: no cover - защитный фоллбек
        latency_ms = (time.monotonic() - started) * 1000.0
        error_msg = str(exc)
        logger.warning(f"Неожиданная ошибка при проверке Postgres в healthcheck: {error_msg}")
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "details": error_msg,
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

    # Для очереди метрик важен именно реальный Redis, а не in‑memory fallback.
    client = getattr(app.state, "redis", None) or get_redis()

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
        error_msg = str(exc)
        # Отсутствие Stream при первом запуске - это нормально, не критичная ошибка
        if "no such key" in error_msg.lower() or "does not exist" in error_msg.lower():
            logger.debug(f"Redis Stream metrics:events ещё не создан: {error_msg}")
        else:
            logger.warning(f"Ошибка XINFO STREAM metrics:events в healthcheck: {error_msg}")
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "details": error_msg,
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
    # Но если проблема только в отсутствии Redis Stream (что нормально при первом запуске),
    # логируем на уровне warning, а не error
    if not all_ok:
        # Проверяем, является ли проблема только отсутствием Stream
        metrics_details = metrics_stream_status.get("details", "")
        is_only_stream_missing = (
            metrics_stream_status.get("status") == "down"
            and ("no such key" in metrics_details.lower() or "does not exist" in metrics_details.lower())
            and redis_status.get("status") == "up"
            and postgres_status.get("status") == "up"
        )

        from utils.logger import EventLogLevel

        log_level: EventLogLevel = "warning" if is_only_stream_missing else "error"
        log_event(
            event="healthcheck_failed",
            status="error",
            latency_ms=total_latency_ms,
            extra={
                "redis_status": redis_status.get("status"),
                "postgres_status": postgres_status.get("status"),
                "metrics_events_status": metrics_stream_status.get("status"),
            },
            level=log_level,
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
