"""
Система метрик для отслеживания производительности на базе PostgreSQL.

Ранее данные хранились в JSON-файле `data/metrics.json`, теперь используется
таблица `metrics` (см. `utils.postgres_schema`).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import asyncpg

from infra.logging.logger import get_logger
from infra.redis.redis_client import RedisClientFactory
from shared.base.base_service import BaseService
from shared.protocols import ILogger, IMetrics

_logger = get_logger(__name__)


@runtime_checkable
class _SupportsExecute(Protocol):
    async def execute(self, query: str, *args: object) -> object:  # pragma: no cover - протокол
        ...


async def record_metric(  # noqa: PLR0913
    db: _SupportsExecute | None = None,
    *,
    pool: asyncpg.Pool | None = None,
    event_type: str,
    user_id: str | None = None,
    prompt_hash: str | None = None,
    image_hash: str | None = None,
    latency_ms: int | None = None,
    status: str | None = None,
    redis_factory: RedisClientFactory | None = None,
) -> None:
    """Публикует единичное событие метрики в очередь (Redis Stream).

    Событие публикуется в Redis Stream `metrics:events` и дополнительно
    сохраняется в таблицу metrics_events PostgreSQL для SQL-запросов.

    Args:
        db: Необязательный объект с методом execute (asyncpg.Connection или пул).
            Используется для записи в Postgres, если pool не указан.
        pool: Необязательный пул подключений PostgreSQL. Требуется, если db не указан.
        event_type: Тип события ('error', 'generation', 'cache_hit', 'cache_miss' и т.п.).

    Raises:
        ValueError: Если ни pool, ни db не указаны.
        user_id: Идентификатор пользователя (например, Telegram user_id).
        prompt_hash: Хэш промпта (sha256, 64-символьное hex-представление).
        image_hash: Хэш изображения (sha256, 64-символьное hex-представление).
        latency_ms: Латентность в миллисекундах.
        status: Статус события ('ok', 'error', 'cached', 'started' и т.п.).

    Note:
        В текущей реализации событие публикуется в Redis Stream
        `metrics:events` с помощью быстрой команды XADD, что минимально
        влияет на горячий путь. При необходимости дальнейшего масштабирования
        можно добавить отдельного воркера, который будет читать события из
        стрима и агрегировать их в Postgres или внешние системы мониторинга.
    """

    # Защита от пустого event_type.
    if not event_type:
        _logger.warning("record_metric: пропущена запись события из-за пустого event_type")
        return

    try:
        # Публикуем событие в Redis Stream `metrics:events`.
        fields: dict[str, Any] = {
            "event_type": event_type,
            "user_id": user_id or "",
            "prompt_hash": prompt_hash or "",
            "image_hash": image_hash or "",
            "latency_ms": latency_ms if latency_ms is not None else "",
            "status": status or "",
        }
        # Используем фабрику Redis для публикации события
        if redis_factory is None:
            raise ValueError("redis_factory is required for record_metric")
        await redis_factory.safe_call("xadd", "metrics:events", fields)

        # Дополнительно стараемся синхронно зафиксировать событие в таблице Postgres.
        # Это делает события наблюдаемыми через SQL (в том числе в тестах и админских
        # diagnostics), при этом ошибка записи в БД не должна влиять на горячий путь.
        try:
            if pool is not None:
                # Используем переданный пул
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO metrics_events (
                            event_type,
                            user_id,
                            prompt_hash,
                            image_hash,
                            latency_ms,
                            status
                        )
                        VALUES ($1, $2, $3, $4, $5, $6);
                        """,
                        event_type,
                        user_id,
                        prompt_hash,
                        image_hash,
                        latency_ms,
                        status,
                    )
            elif db is not None:
                # Используем переданный db (connection или pool)
                await db.execute(
                    """
                    INSERT INTO metrics_events (
                        event_type,
                        user_id,
                        prompt_hash,
                        image_hash,
                        latency_ms,
                        status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6);
                    """,
                    event_type,
                    user_id,
                    prompt_hash,
                    image_hash,
                    latency_ms,
                    status,
                )
            # Если ни pool, ни db не указаны, пропускаем запись в БД (best-effort)
            # Это допустимо, так как событие уже записано в Redis Stream
        except Exception as db_exc:  # pragma: no cover - best-effort запись в БД
            _logger.warning(
                f"record_metric: не удалось синхронно сохранить событие метрики в Postgres: {db_exc}",
            )

        _logger.info(
            "Событие метрики записано: "
            f"type={event_type} prompt={prompt_hash} user={user_id} image={image_hash} "
            f"latency_ms={latency_ms} status={status}",
        )
    except Exception as exc:  # pragma: no cover - защитное логирование и fallback
        _logger.error(
            f"record_metric: не удалось опубликовать событие метрики в Redis Stream: {exc}",
            exc_info=True,
        )
        # Fallback: при недоступности очереди можем (опционально) писать напрямую в Postgres.
        try:
            if pool is not None:
                # Используем переданный пул
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO metrics_events (
                            event_type,
                            user_id,
                            prompt_hash,
                            image_hash,
                            latency_ms,
                            status
                        )
                        VALUES ($1, $2, $3, $4, $5, $6);
                        """,
                        event_type,
                        user_id,
                        prompt_hash,
                        image_hash,
                        latency_ms,
                        status,
                    )
                _logger.info("Событие метрики сохранено напрямую в Postgres (fallback, Redis недоступен)")
            elif db is not None:
                # Используем переданный db (connection или pool)
                await db.execute(
                    """
                    INSERT INTO metrics_events (
                        event_type,
                        user_id,
                        prompt_hash,
                        image_hash,
                        latency_ms,
                        status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6);
                    """,
                    event_type,
                    user_id,
                    prompt_hash,
                    image_hash,
                    latency_ms,
                    status,
                )
                _logger.info("Событие метрики сохранено напрямую в Postgres (fallback, Redis недоступен)")
            else:
                # Если ни pool, ни db не указаны, не можем записать в БД
                _logger.warning(
                    "record_metric: не удалось сохранить событие метрики - "
                    "Redis недоступен и не указаны pool или db параметры"
                )
        except Exception as db_exc:  # pragma: no cover - двойной защитный контур
            _logger.error(
                f"record_metric: не удалось сохранить событие метрики даже в Postgres: {db_exc}",
                exc_info=True,
            )


class Metrics(BaseService, IMetrics):
    """
    Репозиторий метрик производительности.

    Все значения агрегируются в одной строке с id=1, что достаточно для
    текущих сценариев мониторинга.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        logger: ILogger,
        redis_factory: RedisClientFactory | None = None,
    ) -> None:
        """Инициализирует репозиторий метрик.

        Args:
            pool: Пул подключений PostgreSQL.
            logger: Экземпляр логгера для использования в сервисе.
            redis_factory: Фабрика Redis клиента (опционально).
        """
        super().__init__(logger)
        self._pool = pool
        self._redis_factory = redis_factory

    async def _ensure_row(self) -> None:
        """Гарантирует наличие базовой строки метрик (id=1).

        Создаёт строку с id=1 в таблице metrics, если её ещё нет.
        Используется перед операциями обновления метрик.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO metrics (id)
                VALUES (1)
                ON CONFLICT (id) DO NOTHING;
                """,
            )

    async def increment_generation_success_with_pool(self) -> None:
        """Увеличивает счётчик успешных генераций, получая connection из pool.

        Helper-метод для использования вне UoW контекста.
        """
        async with self._pool.acquire() as conn:
            await self.increment_generation_success(connection=conn)

    async def increment_generation_failed_with_pool(self) -> None:
        """Увеличивает счётчик неудачных генераций, получая connection из pool.

        Helper-метод для использования вне UoW контекста.
        """
        async with self._pool.acquire() as conn:
            await self.increment_generation_failed(connection=conn)

    async def increment_dispatch_success_with_pool(self) -> None:
        """Увеличивает счётчик успешных отправок, получая connection из pool.

        Helper-метод для использования вне UoW контекста.
        """
        async with self._pool.acquire() as conn:
            await self.increment_dispatch_success(connection=conn)

    async def increment_dispatch_failed_with_pool(self) -> None:
        """Увеличивает счётчик неудачных отправок, получая connection из pool.

        Helper-метод для использования вне UoW контекста.
        """
        async with self._pool.acquire() as conn:
            await self.increment_dispatch_failed(connection=conn)

    async def increment_generation_success(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик успешных генераций изображений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        try:
            await self._ensure_row()
            await connection.execute(
                "UPDATE metrics SET generations_success = generations_success + 1 WHERE id = 1;",
            )
            self.logger.debug(
                "Записана метрика: increment_generation_success",
                event="metric_recorded",
                status="success",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при записи метрики increment_generation_success: {e}",
                event="metric_record_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def increment_generation_failed(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик неудачных генераций изображений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        try:
            await self._ensure_row()
            await connection.execute(
                "UPDATE metrics SET generations_failed = generations_failed + 1 WHERE id = 1;",
            )
            self.logger.debug(
                "Записана метрика: increment_generation_failed",
                event="metric_recorded",
                status="failed",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при записи метрики increment_generation_failed: {e}",
                event="metric_record_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def add_generation_time(self, seconds: float, connection: asyncpg.Connection | None = None) -> None:
        """Добавляет время генерации к общему времени генераций.

        Args:
            seconds: Время генерации в секундах для добавления.
            connection: Соединение БД для использования в транзакции (опционально).

        Note:
            Метод используется в тестах для проверки расчета среднего времени генерации.
            Использует best-effort семантику: ошибки логируются, но не пробрасываются.
        """
        try:
            await self._ensure_row()
            if connection is not None:
                await connection.execute(
                    "UPDATE metrics SET generations_total_time = generations_total_time + $1 WHERE id = 1;",
                    float(seconds),
                )
            else:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE metrics SET generations_total_time = generations_total_time + $1 WHERE id = 1;",
                        float(seconds),
                    )
            self.logger.debug(
                "Записана метрика: add_generation_time",
                event="metric_recorded",
                status="success",
                seconds=seconds,
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при записи метрики add_generation_time: {e}",
                event="metric_record_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def increment_dispatch_success(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик успешных отправок сообщений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        try:
            await self._ensure_row()
            await connection.execute(
                "UPDATE metrics SET dispatch_success = dispatch_success + 1 WHERE id = 1;",
            )
            self.logger.debug(
                "Записана метрика: increment_dispatch_success",
                event="metric_recorded",
                status="success",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при записи метрики increment_dispatch_success: {e}",
                event="metric_record_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def increment_dispatch_failed(self, connection: asyncpg.Connection) -> None:
        """Увеличивает счётчик неудачных отправок сообщений.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        try:
            await self._ensure_row()
            await connection.execute(
                "UPDATE metrics SET dispatch_failed = dispatch_failed + 1 WHERE id = 1;",
            )
            self.logger.debug(
                "Записана метрика: increment_dispatch_failed",
                event="metric_recorded",
                status="failed",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при записи метрики increment_dispatch_failed: {e}",
                event="metric_record_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def _increment_circuit_breaker_trip(self, connection: asyncpg.Connection | None = None) -> None:
        """Увеличивает счётчик срабатываний circuit breaker (внутренний метод).

        Args:
            connection: Соединение БД для использования в транзакции (опционально).

        Note:
            Внутренний метод, используется только внутри record_circuit_breaker_trip().
            Использует best-effort семантику: ошибки логируются, но не пробрасываются.
        """
        try:
            await self._ensure_row()
            if connection is not None:
                await connection.execute(
                    "UPDATE metrics SET circuit_breaker_trips = circuit_breaker_trips + 1 WHERE id = 1;",
                )
            else:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE metrics SET circuit_breaker_trips = circuit_breaker_trips + 1 WHERE id = 1;",
                    )
            self.logger.debug(
                "Записана метрика: increment_circuit_breaker_trip",
                event="metric_recorded",
                status="circuit_breaker_trip",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при записи метрики increment_circuit_breaker_trip: {e}",
                event="metric_record_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def increment_cache_hit(self) -> None:
        """Увеличивает счётчик попаданий в кэш.

        В текущей реализации используется record_metric для записи события в Redis Stream.
        Для совместимости с протоколом IMetrics метод существует, но не обновляет
        агрегированные метрики в таблице metrics (это делается через record_metric).

        Raises:
            Exception: При ошибке доступа к базе данных или Redis.
        """
        try:
            # Используем record_metric для записи события cache_hit, передавая пул явно
            await record_metric(
                pool=self._pool,
                event_type="cache_hit",
                status="hit",
                redis_factory=self._redis_factory,
            )
            self.logger.debug(
                "Записана метрика: increment_cache_hit",
                event="metric_recorded",
                status="cache_hit",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при записи метрики increment_cache_hit: {e}",
                event="metric_record_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    async def record_circuit_breaker_trip(self) -> None:
        """Увеличивает счётчик срабатываний circuit breaker.

        Реализация метода протокола IMetrics. Использует внутренний метод
        _increment_circuit_breaker_trip() для фактической записи метрики.

        Note:
            Метод использует best-effort семантику: ошибки логируются, но не пробрасываются.
            Это гарантирует, что сбои метрик не влияют на основную бизнес-логику.
        """
        await self._increment_circuit_breaker_trip()

    async def get_summary(self) -> dict[str, Any]:
        """Возвращает сводку всех метрик производительности.

        Returns:
            Словарь с ключами:
            - generations_total: общее количество генераций
            - generations_success: количество успешных генераций
            - generations_failed: количество неудачных генераций
            - generations_retries: количество повторных попыток
            - average_generation_time: среднее время генерации в секундах (строка)
            - dispatches_success: количество успешных отправок
            - dispatches_failed: количество неудачных отправок
            - circuit_breaker_trips: количество срабатываний circuit breaker

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        try:
            await self._ensure_row()
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        generations_success,
                        generations_failed,
                        generations_retries,
                        generations_total_time,
                        dispatch_success,
                        dispatch_failed,
                        circuit_breaker_trips
                    FROM metrics
                    WHERE id = 1;
                    """,
                )

            if row is None:  # pragma: no cover - защитный фоллбек
                return {
                    "generations_total": 0,
                    "generations_success": 0,
                    "generations_failed": 0,
                    "generations_retries": 0,
                    "average_generation_time": "0.00s",
                    "dispatches_success": 0,
                    "dispatches_failed": 0,
                    "circuit_breaker_trips": 0,
                }

            gen_success = int(row["generations_success"])
            gen_failed = int(row["generations_failed"])
            gen_retries = int(row["generations_retries"])
            total_time = float(row["generations_total_time"])
            disp_success = int(row["dispatch_success"])
            disp_failed = int(row["dispatch_failed"])
            trips = int(row["circuit_breaker_trips"])

            total_gen = gen_success + gen_failed
            avg_time = total_time / total_gen if total_gen else 0.0

            return {
                "generations_total": total_gen,
                "generations_success": gen_success,
                "generations_failed": gen_failed,
                "generations_retries": gen_retries,
                "average_generation_time": f"{avg_time:.2f}s",
                "dispatches_success": disp_success,
                "dispatches_failed": disp_failed,
                "circuit_breaker_trips": trips,
            }
        except Exception as e:
            self.logger.warning(
                f"Ошибка при получении сводки метрик: {e}",
                event="metric_summary_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            # Возвращаем пустую сводку при ошибке
            return {
                "generations_total": 0,
                "generations_success": 0,
                "generations_failed": 0,
                "generations_retries": 0,
                "average_generation_time": "0.00s",
                "dispatches_success": 0,
                "dispatches_failed": 0,
                "circuit_breaker_trips": 0,
            }


async def get_daily_generation_stats(pool: asyncpg.Pool, days: int = 7) -> list[dict[str, Any]]:
    """Возвращает агрегированную статистику генераций по дням.

    Для каждого дня рассчитываются:
    - количество успешных генераций;
    - средняя латентность (ms) по успешным генерациям.

    Args:
        days: Количество дней для анализа (по умолчанию 7).
        pool: Пул подключений PostgreSQL (обязательный параметр).

    Returns:
        Список словарей с ключами:
        - day: дата (datetime)
        - generations_ok: количество успешных генераций
        - avg_latency_ms: средняя латентность в миллисекундах (или None)

    Raises:
        ValueError: Если pool равен None.
        Exception: При ошибке доступа к базе данных PostgreSQL.
    """
    if pool is None:
        raise ValueError("pool не может быть None. Передайте пул подключений PostgreSQL через Dependency Injection.")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                date_trunc('day', timestamp) AS day,
                COUNT(*) FILTER (
                    WHERE event_type = 'generation' AND status = 'ok'
                ) AS generations_ok,
                AVG(latency_ms) FILTER (
                    WHERE event_type = 'generation'
                      AND status = 'ok'
                      AND latency_ms IS NOT NULL
                ) AS avg_latency_ms
            FROM metrics_events
            WHERE timestamp >= NOW() - ($1 || ' days')::interval
            GROUP BY date_trunc('day', timestamp)
            ORDER BY day DESC;
            """,
            str(days),
        )

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "day": row["day"],
                "generations_ok": int(row["generations_ok"] or 0),
                "avg_latency_ms": float(row["avg_latency_ms"]) if row["avg_latency_ms"] is not None else None,
            },
        )
    return result


async def get_top_prompts(pool: asyncpg.Pool, limit: int = 10) -> list[dict[str, Any]]:
    """Возвращает топ промптов по количеству успешных генераций.

    Args:
        limit: Максимальное количество строк в выдаче (по умолчанию 10).
        pool: Пул подключений PostgreSQL (обязательный параметр).

    Returns:
        Список словарей с ключами:
        - prompt_hash: хэш промпта
        - generations_ok: количество успешных генераций
        - avg_latency_ms: средняя латентность в миллисекундах (или None)

    Raises:
        ValueError: Если pool равен None.
        Exception: При ошибке доступа к базе данных PostgreSQL.
    """
    if pool is None:
        raise ValueError("pool не может быть None. Передайте пул подключений PostgreSQL через Dependency Injection.")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                prompt_hash,
                COUNT(*) FILTER (
                    WHERE event_type = 'generation' AND status = 'ok'
                ) AS generations_ok,
                AVG(latency_ms) FILTER (
                    WHERE event_type = 'generation'
                      AND status = 'ok'
                      AND latency_ms IS NOT NULL
                ) AS avg_latency_ms
            FROM metrics_events
            WHERE prompt_hash IS NOT NULL
            GROUP BY prompt_hash
            ORDER BY generations_ok DESC
            LIMIT $1;
            """,
            int(limit),
        )

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "prompt_hash": row["prompt_hash"],
                "generations_ok": int(row["generations_ok"] or 0),
                "avg_latency_ms": float(row["avg_latency_ms"]) if row["avg_latency_ms"] is not None else None,
            },
        )
    return result
