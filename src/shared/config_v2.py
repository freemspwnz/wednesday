"""
Модуль конфигурации приложения v2 на основе Pydantic BaseSettings.

Содержит вложенные модели конфигурации для всех модулей приложения.
Поддерживает чтение секретов из файлов через переменные *_FILE.
"""

import os
from pathlib import Path
from typing import ClassVar

import aiohttp
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret_file(file_path: str) -> str | None:
    """Читает секрет из файла.

    Args:
        file_path: Путь к файлу с секретом.

    Returns:
        Содержимое файла без пробельных символов или None при ошибке.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _get_env_value(name: str) -> str | None:
    """Получает значение переменной окружения с поддержкой *_FILE секретов.

    Порядок проверки:
    1. Проверяет переменную окружения с суффиксом _FILE
    2. Если файл найден, читает его содержимое
    3. Если файл не найден или не задан, проверяет обычную переменную окружения

    Args:
        name: Имя переменной окружения.

    Returns:
        Значение переменной или None, если не найдено.
    """
    # Проверяем *_FILE переменную
    file_var = os.getenv(f"{name}_FILE")
    if file_var:
        value = _read_secret_file(file_var)
        if value is not None:
            return value

    # Проверяем обычную переменную окружения
    return os.getenv(name)


class HttpTimeoutConfig(BaseSettings):
    """Конфигурация таймаутов для HTTP-запросов."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    total: int = Field(default=60, description="Общий таймаут запроса в секундах")
    connect: int = Field(default=10, description="Таймаут установления соединения в секундах")
    sock_read: int = Field(default=30, description="Таймаут чтения данных из сокета в секундах")

    def to_client_timeout(self) -> aiohttp.ClientTimeout:
        """Преобразует в aiohttp.ClientTimeout.

        Returns:
            Экземпляр aiohttp.ClientTimeout с настроенными таймаутами.
        """
        return aiohttp.ClientTimeout(
            total=self.total,
            connect=self.connect,
            sock_read=self.sock_read,
        )


class TelegramConfig(BaseSettings):
    """Конфигурация Telegram бота."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", extra="ignore")

    bot_token: str | None = Field(default=None, alias="BOT_TOKEN")
    chat_id: str | None = Field(default=None, alias="CHAT_ID")
    admin_chat_id: str | None = Field(default=None, alias="ADMIN_CHAT_ID")
    proxy_url: str | None = Field(default=None, alias="PROXY_URL")
    vless_url: str | None = Field(default=None, alias="VLESS_URL")
    vless_proxy: str | None = Field(default=None, alias="VLESS_PROXY")

    @field_validator("bot_token", mode="before")
    @classmethod
    def _read_bot_token(cls, v: str | None) -> str | None:
        """Читает токен бота из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("TELEGRAM_BOT_TOKEN")

    @field_validator("chat_id", mode="before")
    @classmethod
    def _read_chat_id(cls, v: str | None) -> str | None:
        """Читает chat_id из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("CHAT_ID")

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def _read_admin_chat_id(cls, v: str | None) -> str | None:
        """Читает admin_chat_id из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("ADMIN_CHAT_ID")

    @field_validator("proxy_url", mode="before")
    @classmethod
    def _read_proxy_url(cls, v: str | None) -> str | None:
        """Читает proxy_url из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("TELEGRAM_PROXY_URL")

    @field_validator("vless_url", mode="before")
    @classmethod
    def _read_vless_url(cls, v: str | None) -> str | None:
        """Читает vless_url из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("TELEGRAM_VLESS_URL")

    @field_validator("vless_proxy", mode="before")
    @classmethod
    def _read_vless_proxy(cls, v: str | None) -> str | None:
        """Читает vless_proxy из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("TELEGRAM_VLESS_PROXY")


class KandinskyConfig(BaseSettings):
    """Конфигурация для Kandinsky клиента."""

    model_config = SettingsConfigDict(env_prefix="KANDINSKY_", extra="ignore")

    api_key: str | None = Field(default=None, alias="API_KEY")
    secret_key: str | None = Field(default=None, alias="SECRET_KEY")
    base_url: str = Field(default="https://api-key.fusionbrain.ai", alias="BASE_URL")
    generation_timeout: HttpTimeoutConfig = Field(
        default_factory=lambda: HttpTimeoutConfig(
            total=int(_get_env_value("KANDINSKY_GENERATION_TIMEOUT_TOTAL") or "60"),
            connect=int(_get_env_value("KANDINSKY_GENERATION_TIMEOUT_CONNECT") or "10"),
            sock_read=int(_get_env_value("KANDINSKY_GENERATION_TIMEOUT_SOCK_READ") or "30"),
        )
    )
    check_timeout: HttpTimeoutConfig = Field(
        default_factory=lambda: HttpTimeoutConfig(
            total=int(_get_env_value("KANDINSKY_CHECK_TIMEOUT_TOTAL") or "15"),
            connect=int(_get_env_value("KANDINSKY_CHECK_TIMEOUT_CONNECT") or "5"),
            sock_read=int(_get_env_value("KANDINSKY_CHECK_TIMEOUT_SOCK_READ") or "10"),
        )
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _read_api_key(cls, v: str | None) -> str | None:
        """Читает API ключ из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("KANDINSKY_API_KEY")

    @field_validator("secret_key", mode="before")
    @classmethod
    def _read_secret_key(cls, v: str | None) -> str | None:
        """Читает secret ключ из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("KANDINSKY_SECRET_KEY")


class GigaChatConfig(BaseSettings):
    """Конфигурация для GigaChat клиента."""

    model_config = SettingsConfigDict(env_prefix="GIGACHAT_", extra="ignore")

    auth_url: str = Field(
        default="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        alias="AUTH_URL",
    )
    api_url: str = Field(
        default="https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        alias="API_URL",
    )
    models_url: str = Field(
        default="https://gigachat.devices.sberbank.ru/api/v1/models",
        alias="MODELS_URL",
    )
    authorization_key: str = Field(default="", alias="AUTHORIZATION_KEY")
    scope: str = Field(default="GIGACHAT_API_PERS", alias="SCOPE")
    model: str = Field(default="GigaChat", alias="MODEL")
    cert_path: str | None = Field(default=None, alias="CERT_PATH")
    verify_ssl: bool | str = Field(default=True, alias="VERIFY_SSL")
    prompt_timeout: HttpTimeoutConfig = Field(
        default_factory=lambda: HttpTimeoutConfig(
            total=int(_get_env_value("GIGACHAT_PROMPT_TIMEOUT_TOTAL") or "60"),
            connect=int(_get_env_value("GIGACHAT_PROMPT_TIMEOUT_CONNECT") or "10"),
            sock_read=int(_get_env_value("GIGACHAT_PROMPT_TIMEOUT_SOCK_READ") or "30"),
        )
    )
    models_timeout: HttpTimeoutConfig = Field(
        default_factory=lambda: HttpTimeoutConfig(
            total=int(_get_env_value("GIGACHAT_MODELS_TIMEOUT_TOTAL") or "30"),
            connect=int(_get_env_value("GIGACHAT_MODELS_TIMEOUT_CONNECT") or "10"),
            sock_read=int(_get_env_value("GIGACHAT_MODELS_TIMEOUT_SOCK_READ") or "20"),
        )
    )
    token_timeout: HttpTimeoutConfig = Field(
        default_factory=lambda: HttpTimeoutConfig(
            total=int(_get_env_value("GIGACHAT_TOKEN_TIMEOUT_TOTAL") or "60"),
            connect=int(_get_env_value("GIGACHAT_TOKEN_TIMEOUT_CONNECT") or "10"),
            sock_read=int(_get_env_value("GIGACHAT_TOKEN_TIMEOUT_SOCK_READ") or "30"),
        )
    )

    @field_validator("authorization_key", mode="before")
    @classmethod
    def _read_authorization_key(cls, v: str | None) -> str | None:
        """Читает authorization key из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("GIGACHAT_AUTHORIZATION_KEY") or ""

    @field_validator("cert_path", mode="before")
    @classmethod
    def _validate_cert_path(cls, v: str | None) -> str | None:
        """Валидирует путь к сертификату."""
        if not v:
            return None
        cert_file = Path(v)
        if cert_file.exists():
            return str(cert_file.absolute())
        return None

    @field_validator("verify_ssl", mode="before")
    @classmethod
    def _validate_verify_ssl(cls, v: str | bool | None) -> bool | str:
        """Валидирует настройку verify_ssl."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            # Если задан cert_path, возвращаем его
            cert_path = _get_env_value("GIGACHAT_CERT_PATH")
            if cert_path and Path(cert_path).exists():
                return cert_path
            # Иначе проверяем флаг
            return v.lower() in {"true", "1", "yes", "on"}
        return True


class PostgresConfig(BaseSettings):
    """Конфигурация для PostgreSQL."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    user: str = Field(alias="USER")
    password: str = Field(alias="PASSWORD")
    db: str = Field(alias="DB")
    host: str = Field(default="localhost", alias="HOST")
    port: int = Field(default=5432, alias="PORT")

    @field_validator("user", mode="before")
    @classmethod
    def _read_user(cls, v: str | None) -> str:
        """Читает имя пользователя из переменной окружения или файла."""
        if v is not None:
            return v
        value = _get_env_value("POSTGRES_USER")
        if not value:
            raise ValueError("POSTGRES_USER не задан")
        return value

    @field_validator("password", mode="before")
    @classmethod
    def _read_password(cls, v: str | None) -> str:
        """Читает пароль из переменной окружения или файла."""
        if v is not None:
            return v
        value = _get_env_value("POSTGRES_PASSWORD")
        if not value:
            raise ValueError("POSTGRES_PASSWORD не задан")
        return value

    @field_validator("db", mode="before")
    @classmethod
    def _read_db(cls, v: str | None) -> str:
        """Читает имя БД из переменной окружения или файла."""
        if v is not None:
            return v
        value = _get_env_value("POSTGRES_DB")
        if not value:
            raise ValueError("POSTGRES_DB не задан")
        return value


class RedisConfig(BaseSettings):
    """Конфигурация для Redis."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: str | None = Field(default=None, alias="URL")
    host: str = Field(default="localhost", alias="HOST")
    port: int = Field(default=6379, alias="PORT")
    db: int = Field(default=0, alias="DB")
    password: str | None = Field(default=None, alias="PASSWORD")

    @field_validator("password", mode="before")
    @classmethod
    def _read_password(cls, v: str | None) -> str | None:
        """Читает пароль из переменной окружения или файла."""
        if v is not None:
            return v
        return _get_env_value("REDIS_PASSWORD")


class SchedulerConfig(BaseSettings):
    """Конфигурация для планировщика задач."""

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_", extra="ignore")

    # Константы для валидации
    TIME_FORMAT_LENGTH = 5
    HOURS_IN_DAY = 24
    MINUTES_IN_HOUR = 60
    DAYS_IN_WEEK = 7

    send_times: list[str] = Field(
        default_factory=lambda: ["09:00", "12:00", "18:00"],
        alias="SEND_TIMES",
    )
    tz: str = Field(default="Europe/Amsterdam", alias="TZ")
    wednesday_day: int = Field(default=2, alias="WEDNESDAY_DAY")

    @field_validator("send_times", mode="before")
    @classmethod
    def _parse_send_times(cls, v: str | list[str] | None) -> list[str]:
        """Парсит времена отправки из строки."""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            times = [t.strip() for t in v.split(",")]
            validated = []
            for t in times:
                if len(t) == cls.TIME_FORMAT_LENGTH and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit():
                    h, m = int(t[:2]), int(t[3:])
                    if 0 <= h < cls.HOURS_IN_DAY and 0 <= m < cls.MINUTES_IN_HOUR:
                        validated.append(t)
            return validated if validated else ["09:00", "12:00", "18:00"]
        return ["09:00", "12:00", "18:00"]

    @field_validator("wednesday_day", mode="before")
    @classmethod
    def _validate_wednesday_day(cls, v: int | str | None) -> int:
        """Валидирует день недели."""
        if isinstance(v, int):
            if 0 <= v < cls.DAYS_IN_WEEK:
                return v
        elif isinstance(v, str):
            try:
                day = int(v)
                if 0 <= day < cls.DAYS_IN_WEEK:
                    return day
            except ValueError:
                pass
        return 2


class SentryConfig(BaseSettings):
    """Конфигурация для Sentry."""

    model_config = SettingsConfigDict(env_prefix="SENTRY_", extra="ignore")

    dsn: str | None = Field(default=None, alias="DSN")
    environment: str | None = Field(default=None, alias="ENVIRONMENT")
    release: str | None = Field(default=None, alias="RELEASE")


class RetryConfig(BaseSettings):
    """Конфигурация для retry механизмов."""

    model_config = SettingsConfigDict(env_prefix="RETRY_", extra="ignore")

    standard_max_attempts: int = Field(default=3, alias="STANDARD_MAX_ATTEMPTS")
    critical_max_attempts: int = Field(default=5, alias="CRITICAL_MAX_ATTEMPTS")
    optional_max_attempts: int = Field(default=2, alias="OPTIONAL_MAX_ATTEMPTS")
    multiplier: float = Field(default=1.0, alias="MULTIPLIER")
    min_wait: float = Field(default=2.0, alias="MIN_WAIT")
    max_wait: float = Field(default=30.0, alias="MAX_WAIT")

    @field_validator("critical_max_attempts", mode="before")
    @classmethod
    def _read_critical_max_attempts(cls, v: int | str | None) -> int:
        """Читает critical_max_attempts с fallback на MAX_ATTEMPTS."""
        if v is not None:
            return int(v)
        value = _get_env_value("RETRY_CRITICAL_MAX_ATTEMPTS") or _get_env_value("RETRY_MAX_ATTEMPTS")
        return int(value) if value else 5


class CircuitBreakerConfig(BaseSettings):
    """Конфигурация для circuit breaker."""

    model_config = SettingsConfigDict(env_prefix="CIRCUIT_BREAKER_", extra="ignore")

    threshold: int = Field(default=5, alias="THRESHOLD")
    window: int = Field(default=300, alias="WINDOW")
    cooldown: int | None = Field(default=None, alias="COOLDOWN")


class AppSettingsConfig(BaseSettings):
    """Настройки приложения для DI."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    admin_chat_id: int | None = None
    chat_id: int | None = None
    scheduler_send_times: list[str] = Field(default_factory=lambda: ["09:00", "12:00", "18:00"])
    frog_rate_limit_minutes: int = Field(default=5)
    frog_rate_limit_window_seconds: int = Field(default=60)
    frog_rate_limit_max_requests: int = Field(default=10)
    scheduler_tz: str = Field(default="Europe/Amsterdam")
    time_format_length: int = Field(default=5)

    @model_validator(mode="after")
    def _parse_chat_ids(self) -> "AppSettingsConfig":
        """Парсит chat_id и admin_chat_id из строк в int."""
        telegram_config = TelegramConfig()
        if telegram_config.admin_chat_id:
            try:
                self.admin_chat_id = int(telegram_config.admin_chat_id)
            except (ValueError, TypeError):
                self.admin_chat_id = None
        if telegram_config.chat_id:
            try:
                self.chat_id = int(telegram_config.chat_id)
            except (ValueError, TypeError):
                self.chat_id = None
        if telegram_config.chat_id:
            scheduler_config = SchedulerConfig()
            self.scheduler_send_times = scheduler_config.send_times
            self.scheduler_tz = scheduler_config.tz
        return self


class ImageConfig:
    """Константы для настройки генерации изображений."""

    FROG_PROMPTS: ClassVar[list[str]] = [
        "cute cartoon frog, green, sitting on a mushroom",
        "funny cartoon frog, green, jumping with excitement",
        "cool cartoon frog, green, wearing sunglasses",
        "sleepy cartoon frog, green, yawning in bed",
        "dancing cartoon frog, green, moving to music",
        "superhero cartoon frog, green, with cape flying",
        "chef cartoon frog, green, cooking in kitchen",
        "scientist cartoon frog, green, with test tubes",
        "artist cartoon frog, green, painting pictures",
        "musician cartoon frog, green, playing guitar",
        "astronaut cartoon frog, green, in space suit",
        "detective cartoon frog, green, with magnifying glass",
        "pirate cartoon frog, green, with eye patch and hat",
        "knight cartoon frog, green, with sword and shield",
        "wizard cartoon frog, green, with magic wand",
    ]

    STYLES: ClassVar[list[str]] = [
        "cartoon, cute, friendly, bright colors",
        "cartoon, funny, expressive, vibrant",
        "cartoon, cool, stylish, modern",
        "cartoon, adorable, charming, detailed",
        "cartoon, energetic, dynamic, colorful",
        "cartoon, heroic, powerful, dramatic",
        "cartoon, creative, artistic, imaginative",
    ]

    WIDTH = 1024
    HEIGHT = 1024

    CAPTIONS: ClassVar[list[str]] = [
        "It's Wednesday, my dudes!",
        "Среда, мои чуваки!",
    ]


class PromptFallbackConfig:
    """Конфигурация для fallback промптов генерации изображений."""

    def __init__(self, frog_prompts: list[str], styles: list[str]) -> None:
        """Инициализирует конфигурацию fallback промптов.

        Args:
            frog_prompts: Список промптов для жабы.
            styles: Список стилей.
        """
        self.frog_prompts = frog_prompts
        self.styles = styles


class ConfigV2(BaseSettings):
    """Главная модель конфигурации приложения v2.

    Содержит все вложенные модели конфигурации для различных модулей.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    kandinsky: KandinskyConfig = Field(default_factory=KandinskyConfig)
    gigachat: GigaChatConfig = Field(default_factory=GigaChatConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    sentry: SentryConfig = Field(default_factory=SentryConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    # Дополнительные настройки
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    prometheus_exporter_port: int | None = Field(default=None, alias="PROMETHEUS_EXPORTER_PORT")
    healthcheck_port: int | None = Field(default=None, alias="HEALTHCHECK_PORT")
    generation_timeout: int = Field(default=60, alias="GENERATION_TIMEOUT")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")

    @field_validator("prometheus_exporter_port", mode="before")
    @classmethod
    def _validate_prometheus_port(cls, v: int | str | None) -> int | None:
        """Валидирует порт Prometheus."""
        if v is None:
            return None
        try:
            port = int(v)
            return port if port > 0 else None
        except (ValueError, TypeError):
            return None

    @field_validator("healthcheck_port", mode="before")
    @classmethod
    def _validate_healthcheck_port(cls, v: int | str | None) -> int | None:
        """Валидирует порт healthcheck."""
        if v is None:
            return None
        try:
            port = int(v)
            return port if port > 0 else None
        except (ValueError, TypeError):
            return None
