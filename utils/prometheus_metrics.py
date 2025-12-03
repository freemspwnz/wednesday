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

from typing import Final

from prometheus_client import Counter, Gauge, Histogram

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
    """
    Обновляет Gauge длины очереди генераций.

    Args:
        length: Текущее количество ожидающих задач генерации.
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
