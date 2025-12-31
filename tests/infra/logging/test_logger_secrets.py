from __future__ import annotations

import json
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest

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


from infra.logging.logger import mask_secrets, scrub  # noqa: E402

SECRET_VALUE = "dummy-secret-for-tests"


def _read_all_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    result: list[dict[str, Any]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        data = json.loads(line)
        result.append(data)
    return result


def test_mask_secrets_basic_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Проверяем, что mask_secrets:
    - маскирует только известные длинные секреты;
    - не трогает строки без секретов;
    - не маскирует короткие значения.
    """

    def _fake_get_env(name: str) -> str | None:
        if name == "GIGACHAT_AUTHORIZATION_KEY":
            return SECRET_VALUE
        return None

    # Подменяем env через os.environ, так как utils.config читает os.getenv
    monkeypatch.setenv("GIGACHAT_AUTHORIZATION_KEY", SECRET_VALUE)

    # Строка без секрета не изменяется
    assert mask_secrets("no secrets here") == "no secrets here"

    # Строка с известным секретом должна быть зачищена
    text_with_secret = f"prefix {SECRET_VALUE} suffix"
    masked = mask_secrets(text_with_secret)
    assert SECRET_VALUE not in masked
    assert "****" in masked

    # Короткое значение (менее порога) не должно маскироваться даже если равно секрету из другой конфигурации.
    short_secret = "short_key"
    monkeypatch.setenv("GIGACHAT_AUTHORIZATION_KEY", short_secret)
    text_with_short = f"prefix {short_secret} suffix"
    masked_short = mask_secrets(text_with_short)
    assert masked_short == text_with_short


def test_scrub_nested_structures_and_keywords() -> None:
    """
    Проверяем, что scrub:
    - маскирует значения по ключам, содержащим чувствительные слова;
    - рекурсивно обрабатывает nested-структуры;
    - применяет mask_secrets к строковым значениям.
    """
    original = {
        "token": "VALUE",
        "nested": {
            "password": "VALUE2",
            "other": "keep",
        },
        "list": [
            {"secret_key": "VALUE3"},
            "plain",
        ],
    }

    cleaned = cast(dict[str, Any], scrub(original))

    assert cleaned["token"] == "****"
    assert cleaned["nested"]["password"] == "****"
    assert cleaned["nested"]["other"] == "keep"
    assert cleaned["list"][0]["secret_key"] == "****"
    assert cleaned["list"][1] == "plain"


def test_scrub_large_structure_performance() -> None:
    """
    Простой performance‑тест для scrub: на 2‑5k ключей работа должна занимать
    разумное время (ориентировочно < 1 секунды).
    """
    import time

    large: dict[str, Any] = {}
    for i in range(5000):
        large[f"key_{i}"] = f"value_{i}"
    # Добавляем несколько чувствительных ключей для проверки логики.
    large["access_token"] = "VALUE"
    large["nested"] = {"secret_key": "VALUE2"}

    start = time.perf_counter()
    result = cast(dict[str, Any], scrub(large))
    duration = time.perf_counter() - start

    assert duration < 1.0, f"scrub работает слишком медленно на больших структурах: {duration:.3f}s"
    assert result["access_token"] == "****"
    assert result["nested"]["secret_key"] == "****"
