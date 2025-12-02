from __future__ import annotations

from typing import Any

from prometheus_client import generate_latest

from utils.prometheus_metrics import (
    FROG_GENERATION_LATENCY_SECONDS,
    FROG_GENERATION_QUEUE_LENGTH,
    FROG_GENERATIONS_TOTAL,
    set_generation_queue_length,
)

_EXPECTED_QUEUE_LENGTH = 5.0
_HTTP_OK = 200


def _get_counter_value(child: Any) -> float:
    """
    Возвращает текущее значение счётчика для конкретного набора label'ов.

    Используем внутреннее поле _value, так как публичного API для чтения
    значения отдельного child у prometheus_client нет. Это приемлемо
    только в тестах.
    """
    return float(child._value.get())


def _get_gauge_value(child: Any) -> float:
    """Возвращает текущее значение gauge для конкретного набора label'ов."""
    return float(child._value.get())


def test_frog_generations_total_counter_increments() -> None:
    child = FROG_GENERATIONS_TOTAL.labels(status="success", source="bot")
    before = _get_counter_value(child)

    child.inc()

    after = _get_counter_value(child)
    assert after == before + 1


def test_frog_generation_latency_histogram_observe() -> None:
    # Считаем количество наблюдений для конкретной комбинации label'ов
    # через публичный API collect(), не полагаясь на внутренние атрибуты.
    def _histogram_count() -> float:
        total = 0.0
        for metric in FROG_GENERATION_LATENCY_SECONDS.collect():
            for sample in metric.samples:
                if (
                    sample.name.endswith("_count")
                    and sample.labels.get("status") == "success"
                    and sample.labels.get("source") == "bot"
                ):
                    total += float(sample.value)
        return total

    before_count = _histogram_count()
    FROG_GENERATION_LATENCY_SECONDS.labels(status="success", source="bot").observe(0.5)
    after_count = _histogram_count()

    assert after_count == before_count + 1


def test_frog_generation_queue_length_gauge_set() -> None:
    set_generation_queue_length(int(_EXPECTED_QUEUE_LENGTH), source="bot")
    child = FROG_GENERATION_QUEUE_LENGTH.labels(source="bot")
    assert _get_gauge_value(child) == _EXPECTED_QUEUE_LENGTH


def test_metrics_http_endpoint_serves_metrics() -> None:
    """
    Проверяет, что экспортируемый текст метрик содержит зарегистрированные метрики.

    Вместо реального HTTP‑запроса используем generate_latest(), чтобы избежать
    сетевых флапов в тестовой среде.
    """
    # Генерируем хотя бы одно событие, чтобы метрика точно появилась.
    FROG_GENERATIONS_TOTAL.labels(status="success", source="bot").inc()

    body = generate_latest().decode("utf-8")
    assert "frog_generations_total" in body
