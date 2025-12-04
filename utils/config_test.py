"""
Тестовый слой настроек.

Используется только в тестовом коде (Celery test app, утилиты, e2e‑фикстуры)
и не зависит от боевого модуля utils.config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TestConfig:
    """Настройки для тестовой среды (Redis, Postgres, логирование и пр.)."""

    # Redis для тестового Celery
    celery_test_redis_url: str

    # Базовые параметры Postgres для тестов (используются в фикстурах/скриптах)
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int

    log_level: str


def _build_test_config() -> TestConfig:
    """Создаёт экземпляр TestConfig из переменных окружения."""
    # По умолчанию ориентируемся на docker-compose.test.yml:
    # внутри тестовой сети Redis доступен как redis_test:6379.
    # При необходимости можно переопределить через CELERY_TEST_REDIS_URL.
    celery_test_redis_url = os.getenv("CELERY_TEST_REDIS_URL", "redis://redis_test:6379/1")

    postgres_user = os.getenv("POSTGRES_USER", "test_user")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "test_password_ci_2024")
    postgres_db = os.getenv("POSTGRES_DB", "wednesdaydb_test")
    postgres_host = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))

    log_level = os.getenv("TEST_LOG_LEVEL", "INFO")

    return TestConfig(
        celery_test_redis_url=celery_test_redis_url,
        postgres_user=postgres_user,
        postgres_password=postgres_password,
        postgres_db=postgres_db,
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        log_level=log_level,
    )


config_test = _build_test_config()
