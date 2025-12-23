"""
Прометеевые метрики для бота Wednesday.

Модуль инкапсулирует регистрацию и использование Prometheus‑метрик, чтобы:
- не размазывать детали prometheus_client по коду бота;
- централизованно контролировать имена, label'ы и семантику метрик;
- сохранить согласованность с событиями в `metrics_events` (таблица Postgres).

Важно:
- Модуль безопасен к многократному импорту: регистраторы метрик создаются
  один раз на уровне модуля.
- Метрики именованы в стиле snake_case и используют согласованные label'ы:
  * status — логический статус операции ("success", "failure", "cached", "circuit_breaker_open" и т.п.);
  * source — источник события ("bot", "scheduler", "support_bot" и др.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from prometheus_client import Counter, Gauge, Histogram

if TYPE_CHECKING:
    import asyncpg

# Имена метрик и label'ы подобраны так, чтобы их можно было напрямую
# сопоставлять с колонками таблицы `metrics_events`:
# - event_type='generation' ↔ frog_generations_total;
# - latency_ms           ↔ frog_generation_latency_seconds (преобразуем в секунды);
# - статус события       ↔ label status.

# Счётчик всех попыток генерации изображения жабы.
# label status:
#   - "success"  — успешная генерация и сохранение изображения;
#   - "failure"  — ошибка генерации (HTTP, таймаут, валидация и т.п.);
#   - "skipped"  — генерация пропущена (например, circuit breaker).
# label source:
#   - "bot"        — ручные запросы пользователей (/frog);
#   - "scheduler"  — автоматические рассылки;
#   - другие значения по мере расширения.
FROG_GENERATIONS_TOTAL: Final[Counter] = Counter(
    name="frog_generations_total",
    documentation=(
        "Общее количество попыток генерации изображения жабы "
        "с разбивкой по статусу и источнику (согласовано с metrics_events.event_type='generation')."
    ),
    labelnames=("status", "source"),
)

# Гистограмма латентности генераций в секундах.
# Диапазон бакетов подобран под типичные значения:
# - <1s — кэш / очень быстрый ответ;
# - 1–30s — нормальный диапазон для внешнего API;
# - >30s — аномально высокие значения.
FROG_GENERATION_LATENCY_SECONDS: Final[Histogram] = Histogram(
    name="frog_generation_latency_seconds",
    documentation=(
        "Латентность успешных генераций изображения жабы в секундах "
        "(источник и статус совпадают с frog_generations_total)."
    ),
    labelnames=("status", "source"),
    buckets=(
        0.25,
        0.5,
        1.0,
        2.0,
        5.0,
        10.0,
        20.0,
        30.0,
        60.0,
        120.0,
    ),
)

# Gauge для оценки длины очереди задач генерации.
# В типовом сценарии это может быть Redis Stream, список задач планировщика
# или любая другая структура, где накапливаются задания на генерацию.
# Если в конкретной установке нет явной очереди, обновление Gauge
# можно не вызывать — метрика останется нулевой.
FROG_GENERATION_QUEUE_LENGTH: Final[Gauge] = Gauge(
    name="frog_generation_queue_length",
    documentation=("Текущая длина очереди задач на генерацию жабы (если используется отдельная очередь задач)."),
    labelnames=("source",),
)


def set_generation_queue_length(length: int, source: str = "bot") -> None:
    """Обновляет Gauge длины очереди генераций.

    Args:
        length: Текущее количество ожидающих задач генерации.
            Отрицательные значения автоматически преобразуются в 0.
        source: Источник очереди (по умолчанию 'bot'; может быть 'scheduler' и т.п.).
    """
    length = max(length, 0)
    FROG_GENERATION_QUEUE_LENGTH.labels(source=source).set(float(length))


# Метрики для retry-механик HTTP-запросов
# Счётчик всех retry-попыток
# label service: имя сервиса ("kandinsky", "gigachat")
# label method: имя метода ("generate", "check_api_status" и т.д.)
# label status: статус ("retry" - промежуточная попытка, "failed" - все попытки исчерпаны)
HTTP_RETRIES_TOTAL: Final[Counter] = Counter(
    name="http_retries_total",
    documentation=("Общее количество retry-попыток для HTTP-запросов с разбивкой по сервису, методу и статусу."),
    labelnames=("service", "method", "status"),
)

# Гистограмма времени ожидания между retry-попытками
# label service: имя сервиса
# label method: имя метода
HTTP_RETRY_WAIT_SECONDS: Final[Histogram] = Histogram(
    name="http_retry_wait_seconds",
    documentation=("Время ожидания между retry-попытками в секундах с разбивкой по сервису и методу."),
    labelnames=("service", "method"),
    buckets=(
        0.5,
        1.0,
        2.0,
        4.0,
        8.0,
        16.0,
        30.0,
    ),
)

# Метрики Celery задач
CELERY_TASKS_TOTAL: Final[Counter] = Counter(
    name="celery_tasks_total",
    documentation="Общее количество Celery задач с разбивкой по имени задачи и статусу",
    labelnames=("task_name", "status"),
)

CELERY_TASK_DURATION_SECONDS: Final[Histogram] = Histogram(
    name="celery_task_duration_seconds",
    documentation="Длительность выполнения Celery задач в секундах",
    labelnames=("task_name",),
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

CELERY_TASK_RETRIES_TOTAL: Final[Counter] = Counter(
    name="celery_task_retries_total",
    documentation="Количество retry-попыток для Celery задач",
    labelnames=("task_name",),
)

CELERY_TASK_FAILURES_TOTAL: Final[Counter] = Counter(
    name="celery_task_failures_total",
    documentation="Количество неудачных Celery задач",
    labelnames=("task_name", "error_type"),
)

CELERY_QUEUE_LENGTH: Final[Gauge] = Gauge(
    name="celery_queue_length",
    documentation="Текущая длина очереди Celery",
    labelnames=("queue_name",),
)

CELERY_ACTIVE_TASKS: Final[Gauge] = Gauge(
    name="celery_active_tasks",
    documentation="Количество активных задач в Celery worker",
    labelnames=("worker_name",),
)

# Метрики пула подключений PostgreSQL
POSTGRES_POOL_SIZE: Final[Gauge] = Gauge(
    name="postgres_pool_size",
    documentation="Текущий размер пула подключений PostgreSQL",
)

POSTGRES_POOL_IDLE: Final[Gauge] = Gauge(
    name="postgres_pool_idle",
    documentation="Количество свободных соединений в пуле PostgreSQL",
)

POSTGRES_POOL_ACTIVE: Final[Gauge] = Gauge(
    name="postgres_pool_active",
    documentation="Количество активных соединений в пуле PostgreSQL",
)

POSTGRES_POOL_MAX: Final[Gauge] = Gauge(
    name="postgres_pool_max",
    documentation="Максимальный размер пула подключений PostgreSQL",
)

# Метрики состояния circuit breaker
# Состояние circuit breaker (1 = открыт, 0 = закрыт)
# label key: логический ключ ресурса (например, 'cb:kandinsky_api')
CIRCUIT_BREAKER_STATE: Final[Gauge] = Gauge(
    name="circuit_breaker_state",
    documentation="Состояние circuit breaker (1 = открыт, 0 = закрыт)",
    labelnames=("key",),
)

# Количество ошибок в circuit breaker
# label key: логический ключ ресурса
CIRCUIT_BREAKER_FAILURES: Final[Gauge] = Gauge(
    name="circuit_breaker_failures",
    documentation="Количество ошибок в circuit breaker",
    labelnames=("key",),
)


def update_pool_metrics(pool: asyncpg.Pool) -> None:
    """Обновляет метрики пула подключений PostgreSQL.

    Args:
        pool: Пул подключений PostgreSQL (обязательный параметр).
    """
    from infra.database.postgres_client import get_pool_metrics

    try:
        metrics = get_pool_metrics(pool)
        POSTGRES_POOL_SIZE.set(float(metrics.size))
        POSTGRES_POOL_IDLE.set(float(metrics.idle_size))
        POSTGRES_POOL_ACTIVE.set(float(metrics.active_connections))
        POSTGRES_POOL_MAX.set(float(metrics.max_size))
    except Exception as e:
        # Логируем ошибку, но не прерываем выполнение (best-effort)
        from infra.logging.logger import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Не удалось обновить метрики пула: {e}")
