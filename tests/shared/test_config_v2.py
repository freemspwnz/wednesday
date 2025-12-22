"""Тесты для структуры конфигурации Config."""

from typing import Any

import pytest

from shared.config import (
    Config,
    HttpTimeoutConfig,
    PostgresConfig,
    RedisConfig,
    SchedulerConfig,
)


def test_config_v2_creation_from_env(monkeypatch: Any) -> None:
    """Тест создания Config из переменных окружения."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("KANDINSKY_API_KEY", "test-api-key")
    monkeypatch.setenv("KANDINSKY_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("CHAT_ID", "12345")
    monkeypatch.setenv("ADMIN_CHAT_ID", "54321")
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("GIGACHAT_AUTHORIZATION_KEY", "test-key")
    monkeypatch.setenv("SCHEDULER_SEND_TIMES", "09:00,12:00,18:00")
    monkeypatch.setenv("SCHEDULER_TZ", "Europe/Moscow")

    config = Config()

    assert config.telegram.bot_token == "test-token"
    assert config.kandinsky.api_key == "test-api-key"
    assert config.kandinsky.secret_key == "test-secret-key"
    assert config.telegram.chat_id == "12345"
    assert config.telegram.admin_chat_id == "54321"
    assert config.postgres.user == "test_user"
    assert config.postgres.password == "test_password"
    assert config.postgres.db == "test_db"
    assert config.gigachat.authorization_key == "test-key"
    assert config.scheduler.send_times == ["09:00", "12:00", "18:00"]
    assert config.scheduler.tz == "Europe/Moscow"


def test_config_v2_model_validate(monkeypatch: Any) -> None:
    """Тест создания Config через model_validate."""
    # Устанавливаем минимальные обязательные переменные
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")

    # Создаём через model_validate с минимальными данными
    config_data = {
        "telegram": {
            "bot_token": "test-token",
            "chat_id": "12345",
        },
        "kandinsky": {
            "api_key": "test-api",
            "secret_key": "test-secret",
        },
        "postgres": {
            "user": "test_user",
            "password": "test_password",
            "db": "test_db",
        },
    }

    config = Config.model_validate(config_data)

    assert config.telegram.bot_token == "test-token"
    assert config.telegram.chat_id == "12345"
    assert config.kandinsky.api_key == "test-api"
    assert config.kandinsky.secret_key == "test-secret"
    assert config.postgres.user == "test_user"


def test_config_v2_secret_file_support(monkeypatch: Any, tmp_path: Any) -> None:
    """Тест поддержки чтения секретов из файлов через *_FILE переменные."""
    # Создаём временный файл с секретом
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("secret-from-file")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_FILE", str(secret_file))
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")

    config = Config()

    assert config.telegram.bot_token == "secret-from-file"


def test_config_direct_access(monkeypatch: Any) -> None:
    """Тест прямого доступа к конфигурации через Config."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("KANDINSKY_API_KEY", "test-api")
    monkeypatch.setenv("KANDINSKY_SECRET_KEY", "test-secret")
    monkeypatch.setenv("CHAT_ID", "12345")
    monkeypatch.setenv("ADMIN_CHAT_ID", "54321")
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("GIGACHAT_AUTHORIZATION_KEY", "test-key")
    monkeypatch.setenv("SCHEDULER_SEND_TIMES", "09:00,12:00,18:00")

    config = Config()

    # Тестируем преобразование в старые dataclass'ы
    gigachat_config = config.to_gigachat_config()
    assert gigachat_config.authorization_key == "test-key"

    kandinsky_config = config.to_kandinsky_config()
    assert kandinsky_config.api_key == "test-api"
    assert kandinsky_config.secret_key == "test-secret"

    app_settings = config.to_app_settings()
    assert app_settings.chat_id == 12345
    assert app_settings.admin_chat_id == 54321

    retry_config = config.to_retry_config()
    assert retry_config.standard_max_attempts == 3  # default

    circuit_breaker_config = config.to_circuit_breaker_config()
    assert circuit_breaker_config.threshold == 5  # default


def test_http_timeout_config(monkeypatch: Any) -> None:
    """Тест HttpTimeoutConfig."""
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")

    timeout = HttpTimeoutConfig(total=60, connect=10, sock_read=30)

    assert timeout.total == 60
    assert timeout.connect == 10
    assert timeout.sock_read == 30

    # Тест преобразования в aiohttp.ClientTimeout
    client_timeout = timeout.to_client_timeout()
    assert client_timeout.total == 60
    assert client_timeout.connect == 10
    assert client_timeout.sock_read == 30


def test_scheduler_config_validation(monkeypatch: Any) -> None:
    """Тест валидации SchedulerConfig."""
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")

    # Тест валидных времён
    monkeypatch.setenv("SCHEDULER_SEND_TIMES", "09:00,12:00,18:00")
    scheduler = SchedulerConfig()
    assert scheduler.send_times == ["09:00", "12:00", "18:00"]

    # Тест невалидных времён (должны быть отфильтрованы)
    monkeypatch.setenv("SCHEDULER_SEND_TIMES", "25:00,invalid,09:00")
    scheduler = SchedulerConfig()
    assert "09:00" in scheduler.send_times
    assert "25:00" not in scheduler.send_times
    assert "invalid" not in scheduler.send_times

    # Тест валидации дня недели
    monkeypatch.setenv("SCHEDULER_WEDNESDAY_DAY", "2")
    scheduler = SchedulerConfig()
    assert scheduler.wednesday_day == 2

    # Тест невалидного дня (должен вернуть default)
    monkeypatch.setenv("SCHEDULER_WEDNESDAY_DAY", "10")
    scheduler = SchedulerConfig()
    assert scheduler.wednesday_day == 2  # default


def test_postgres_config_required_fields(monkeypatch: Any) -> None:
    """Тест обязательных полей PostgresConfig."""
    # Без обязательных полей должна быть ошибка
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PostgresConfig()


def test_redis_config_defaults(monkeypatch: Any) -> None:
    """Тест значений по умолчанию для RedisConfig."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("REDIS_PORT", raising=False)
    monkeypatch.delenv("REDIS_DB", raising=False)

    redis_config = RedisConfig()

    assert redis_config.host == "localhost"
    assert redis_config.port == 6379
    assert redis_config.db == 0
    assert redis_config.url is None
