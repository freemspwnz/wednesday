from __future__ import annotations

import json
from io import StringIO

from loguru import logger

from infra.logging.logger import log_event

# Тестовое значение латентности в миллисекундах для проверки сериализации.
LATENCY_TEST_VALUE_MS = 42.0


def test_log_event_produces_structured_json() -> None:
    """Проверяем, что log_event пишет корректный JSON с нужными полями и фильтрует None."""
    buffer = StringIO()

    # В тесте добавляем временный sink с serialize=True, чтобы перехватить JSON‑строку.
    sink_id = logger.add(buffer, serialize=True)
    try:
        log_event(
            event="test_event",
            user_id=123,
            prompt_hash="phash",
            image_id="ihash",
            latency_ms=LATENCY_TEST_VALUE_MS,
            status="ok",
            extra={"foo": "bar", "skip_none": None},
            level="info",
            message="hello",
        )
    finally:
        logger.remove(sink_id)

    raw = buffer.getvalue().strip()
    assert raw, "лог должен содержать хотя бы одну строку JSON"

    data = json.loads(raw)

    # В serialize-формате loguru основные поля находятся внутри ключа "record".
    record = data.get("record")
    assert isinstance(record, dict), "ожидали, что корень JSON содержит ключ 'record' с данными события"

    # Базовые поля loguru (time, level, message) должны присутствовать.
    assert "time" in record
    assert "level" in record
    assert record["message"] == "hello"

    # Стандартные поля обёртки log_event живут в record["extra"].
    extra = record.get("extra") or {}
    assert extra["event"] == "test_event"
    assert extra["user_id"] == "123"  # приводим к строке
    assert extra["prompt_hash"] == "phash"
    assert extra["image_id"] == "ihash"
    assert extra["latency_ms"] == LATENCY_TEST_VALUE_MS
    assert extra["status"] == "ok"

    # Дополнительные поля из extra.
    assert extra["foo"] == "bar"
    # Поля со значением None не должны попадать в JSON.
    assert "skip_none" not in extra
