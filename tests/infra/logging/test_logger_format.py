"""
Unit тесты для формата логов.

Проверяют, что логи имеют правильную структуру JSON и все поля на месте.
"""

import io
import json
import os
from collections.abc import Generator

import pytest

# Минимальный набор обязательных переменных окружения для инициализации config
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")


@pytest.fixture(scope="session", autouse=True)
def celery_worker_ready() -> None:
    """Отключаем ожидание внешнего Celery worker для юнит-тестов."""
    return None


@pytest.fixture(autouse=True)
def _setup_test_postgres() -> Generator[None, None, None]:
    """Отключаем автосоздание/очистку тестовой БД для юнит-тестов логгера."""
    yield


from infra.logging.logger import get_logger  # noqa: E402


def test_log_format_is_valid_json() -> None:
    """Проверяет, что каждая запись лога - валидный JSON."""
    # Перехватываем вывод в StringIO
    buffer = io.StringIO()

    # Настраиваем logger с buffer sink
    logger = get_logger("test")
    logger.add(buffer, serialize=True, level="INFO")  # type: ignore[attr-defined]

    # Логируем тестовое сообщение
    logger.info("test message", extra={"test": "value"})

    # Читаем из buffer
    buffer.seek(0)
    line = buffer.readline().strip()

    # Проверяем, что это валидный JSON и содержит стандартные поля внутри record
    log_entry = json.loads(line)
    record = log_entry.get("record", {})
    assert record, "Log entry must contain 'record'"
    assert "time" in record
    assert "message" in record
    assert "level" in record
    assert "extra" in record


def test_required_fields_in_extra() -> None:
    """Проверяет наличие обязательных полей в extra."""
    buffer = io.StringIO()
    logger = get_logger("test")
    logger.add(buffer, serialize=True, level="INFO")  # type: ignore[attr-defined]

    logger.info("test", extra={"service": "test-service", "env": "test"})

    buffer.seek(0)
    line = buffer.readline().strip()
    log_entry = json.loads(line)
    record = log_entry.get("record", {})
    extra_container = record.get("extra", {})
    extra = extra_container.get("extra", extra_container)

    assert extra["service"] == "test-service"
    assert extra["env"] == "test"


def test_high_cardinality_in_extra() -> None:
    """Проверяет, что high-cardinality поля в extra, не в top-level."""
    buffer = io.StringIO()
    logger = get_logger("test")
    logger.add(buffer, serialize=True, level="INFO")  # type: ignore[attr-defined]

    logger.info("test", extra={"user_id": "u-123", "prompt_hash": "hash"})

    buffer.seek(0)
    line = buffer.readline().strip()
    log_entry = json.loads(line)
    record = log_entry.get("record", {})
    extra_container = record.get("extra", {})
    extra = extra_container.get("extra", extra_container)

    # user_id и prompt_hash должны быть в extra, не в top-level record
    assert "user_id" not in record
    assert "prompt_hash" not in record
    assert extra["user_id"] == "u-123"
    assert extra["prompt_hash"] == "hash"
