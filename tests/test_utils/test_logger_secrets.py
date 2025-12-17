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


from utils.logger import log_event, mask_secrets, scrub, setup_logger  # noqa: E402

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


@pytest.mark.parametrize("testing_env", ["", "0", "false", "no"])
def test_json_logs_do_not_contain_gigachat_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    testing_env: str,
) -> None:
    """
    Интеграционный тест JSON‑логов:
    - подменяем директорию логов на временную;
    - настраиваем GIGACHAT_AUTHORIZATION_KEY на известное значение;
    - генерируем несколько записей, где секрет явно фигурирует в extra и bind;
    - убеждаемся, что секретное значение не попало ни в message, ни в extra.
    """
    # Настраиваем окружение: включаем обычный режим логгера (без TESTING=1)
    if testing_env:
        monkeypatch.setenv("TESTING", testing_env)
    else:
        # Удаляем переменную, если она была установлена
        monkeypatch.delenv("TESTING", raising=False)

    monkeypatch.setenv("GIGACHAT_AUTHORIZATION_KEY", SECRET_VALUE)

    # Гарантируем, что файловые sink-и не отключены принудительно
    monkeypatch.delenv("LOG_TO_STDOUT_ONLY", raising=False)
    # Включаем файловые логи для теста
    monkeypatch.setenv("LOG_TO_FILE", "1")

    # Подменяем директорию логов
    logs_dir = tmp_path / "logs"

    # Патчим константу в модуле, где она используется
    monkeypatch.setattr("utils.logger.LOGS_DIR", logs_dir)

    # Переинициализируем логгер с новой конфигурацией
    setup_logger()

    # Пишем несколько событий в JSON‑sink
    log_event(
        event="test_secret_in_extra",
        extra={"authorization": f"Basic {SECRET_VALUE}"},
        level="info",
        message="message with secret in extra",
    )

    log_event(
        event="test_secret_nested",
        extra={"auth": {"token": SECRET_VALUE}},
        level="info",
        message="nested secret",
    )

    log_event(
        event="test_secret_bind",
        extra={"auth": SECRET_VALUE},
        level="info",
        message="direct bind with secret",
    )

    jsonl_path = logs_dir / "wednesday_bot.events.jsonl"
    records = _read_all_jsonl(jsonl_path)
    assert records, "JSON‑лог должен содержать хотя бы одну запись"

    # Проверяем, что секрет нигде не встретился и что значения по чувствительным ключам
    # заменены на маску "****".
    for data in records:
        record = data.get("record", {})
        serialized = json.dumps(record, ensure_ascii=False)
        assert SECRET_VALUE not in serialized, "Секретное значение не должно присутствовать в JSON‑логах"

        extra = record.get("extra") or {}
        event = extra.get("event")

        if event == "test_secret_in_extra":
            # authorization должен быть замаскирован целиком
            assert extra.get("authorization") == "****"
        elif event == "test_secret_nested":
            # nested токен также должен быть замаскирован
            auth_obj = extra.get("auth") or {}
            assert auth_obj.get("token") == "****"


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
