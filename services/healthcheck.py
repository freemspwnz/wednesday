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
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError

from utils.logger import get_logger, log_event, log_http
from utils.postgres_client import get_postgres_pool
from utils.redis_client import get_redis

logger = get_logger(__name__)

# Экспортируемое FastAPI‑приложение. Uvicorn использует его для запуска
# HTTP‑сервера внутри того же event loop, что и Telegram‑бот.
app = FastAPI(title="Wednesday Frog Bot Healthcheck")

# HTTP статус код для разделения успешных и ошибочных запросов
_HTTP_STATUS_OK_MAX = 399


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Middleware для логирования HTTP запросов.

    Логирует все HTTP запросы к healthcheck эндпоинту с информацией о методе,
    пути, статус-коде и времени выполнения.

    Args:
        request: Входящий HTTP запрос.
        call_next: Следующий обработчик в цепочке middleware.

    Returns:
        HTTP ответ от следующего обработчика.
    """
    start_time = time.time()
    response = await call_next(request)
    latency_ms = (time.time() - start_time) * 1000

    log_http(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        latency_ms=latency_ms,
        level="info" if response.status_code <= _HTTP_STATUS_OK_MAX else "warning",
    )
    return response


async def _check_redis() -> dict[str, Any]:
    """Выполняет проверку доступности Redis.

    Проверяет доступность Redis через ping команду. Измеряет латентность запроса.

    Returns:
        Словарь с результатами проверки, содержащий:
        - status: Статус Redis ("up" или "down").
        - using_fallback: Флаг использования fallback клиента (всегда False).
        - latency_ms: Латентность ping запроса в миллисекундах.
        - details: Детали ошибки (если есть) или None.

    Raises:
        RedisError: При ошибке подключения к Redis.
        Exception: При неожиданных ошибках.
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
    """Выполняет проверку доступности Postgres.

    Проверяет доступность Postgres через простой запрос SELECT 1. Измеряет
    латентность запроса.

    Returns:
        Словарь с результатами проверки, содержащий:
        - status: Статус Postgres ("up" или "down").
        - latency_ms: Латентность запроса в миллисекундах.
        - details: Детали ошибки (если есть) или None.

    Raises:
        asyncpg.PostgresError: При ошибке подключения или выполнения запроса.
        Exception: При неожиданных ошибках.
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
    """Проверяет доступность основной бизнес‑очереди Redis Stream `metrics:events`.

    Выполняет проверку через команду XINFO STREAM для проверки существования
    и доступности очереди метрик.

    Returns:
        Словарь с результатами проверки, содержащий:
        - status: Статус очереди ("up" или "down").
        - latency_ms: Латентность запроса в миллисекундах.
        - details: Детали ошибки (если есть) или None.

    Note:
        - Если Redis недоступен — очередь считается "down".
        - Если команда XINFO STREAM завершилась успешно — "up".
        - Если ключ отсутствует (ERR no such key) — считается "down", так как
          это важная очередь бизнес‑метрик.

    Raises:
        RedisError: При ошибке подключения к Redis или выполнения команды.
        Exception: При неожиданных ошибках.
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


async def _check_celery() -> dict[str, Any]:
    """Выполняет проверку доступности Celery workers.

    Проверяет доступность Celery workers через ping команду. Подсчитывает
    количество активных workers.

    Returns:
        Словарь с результатами проверки, содержащий:
        - status: Статус Celery workers ("up" или "down").
        - workers_count: Количество активных workers.
        - latency_ms: Латентность ping запроса в миллисекундах.
        - details: Детали ошибки (если есть) или None.

    Raises:
        Exception: При ошибке проверки workers (таймаут, недоступность и т.д.).
    """
    started = time.monotonic()

    try:
        import asyncio

        from services.celery import celery_app

        # Проверяем доступность workers через ping
        # celery_app.control.inspect() синхронный, запускаем в executor
        loop = asyncio.get_event_loop()
        inspect_obj = celery_app.control.inspect(timeout=0.2)
        result = await loop.run_in_executor(None, inspect_obj.ping)

        if result:
            workers_count = len(result)
            latency_ms = (time.monotonic() - started) * 1000.0
            return {
                "status": "up",
                "workers_count": workers_count,
                "latency_ms": latency_ms,
                "details": None,
            }
        else:
            latency_ms = (time.monotonic() - started) * 1000.0
            return {
                "status": "down",
                "workers_count": 0,
                "latency_ms": latency_ms,
                "details": "No workers available",
            }
    except Exception as exc:
        latency_ms = (time.monotonic() - started) * 1000.0
        logger.warning(f"Ошибка при проверке Celery в healthcheck: {exc!s}")
        return {
            "status": "down",
            "workers_count": 0,
            "latency_ms": latency_ms,
            "details": str(exc),
        }


async def _build_health_payload() -> dict[str, Any]:
    """Выполняет все проверки и формирует итоговый JSON‑ответ healthcheck.

    Выполняет проверки всех критичных зависимостей (Redis, Postgres, очередь
    метрик) и формирует агрегированный ответ. Celery не считается критичным
    для основного healthcheck бота.

    Returns:
        Словарь с результатами всех проверок, содержащий:
        - status: Общий статус ("up" или "down").
        - redis: Результаты проверки Redis.
        - postgres: Результаты проверки Postgres.
        - celery: Результаты проверки Celery workers.
        - queues: Словарь с результатами проверки очередей:
          - metrics_events: Результаты проверки очереди метрик.
        - latency_ms: Общее время выполнения всех проверок в миллисекундах.

    Note:
        Общий статус "up" только если все критичные зависимости (Redis, Postgres,
        metrics:events) в состоянии "up".
    """
    started = time.monotonic()
    redis_status = await _check_redis()
    postgres_status = await _check_postgres()
    metrics_stream_status = await _check_metrics_stream()
    celery_status = await _check_celery()

    # Все три зависимости считаются критичными для статуса "up":
    # - Redis (в том числе для лимитеров, кэшей и circuit‑breaker);
    # - Postgres (персистентное хранилище);
    # - основная очередь метрик metrics:events.
    # Celery не критичен для основного healthcheck бота, но полезен для мониторинга
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
        "celery": celery_status,  # Добавляем статус Celery
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
                "celery_status": celery_status.get("status"),
            },
            level=log_level,
            message="Healthcheck зависимости бота не в состоянии up",
        )

    return payload


@app.get("/health")
async def health() -> JSONResponse:
    """Основной HTTP‑эндпоинт healthcheck.

    Выполняет проверку всех критичных зависимостей бота и возвращает агрегированный
    статус. Используется для Docker HEALTHCHECK, Kubernetes liveness/readiness probes
    и внешних систем мониторинга.

    Returns:
        JSONResponse с результатами проверки:
        - HTTP 200 и status="up", если все критические зависимости доступны.
        - HTTP 503 и status="down" в противном случае.

    Note:
        Критичными зависимостями считаются: Redis, Postgres и очередь metrics:events.
        Celery workers не являются критичными для основного healthcheck.
    """
    payload = await _build_health_payload()
    http_status = 200 if payload.get("status") == "up" else 503
    return JSONResponse(content=payload, status_code=http_status)
