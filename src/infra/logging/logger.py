"""
Модуль настройки логирования для приложения.
Использует библиотеку loguru для удобного и красивого логирования.
"""

import inspect
import logging
import os
import sys
from collections.abc import Callable
from functools import wraps
from types import FrameType
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar, cast, overload

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger as LoggerType

    from shared.protocols.infrastructure import ILogger

from shared.config import Config
from shared.paths import LOGS_DIR

# Создаём экземпляр Config при импорте модуля
config: Config = Config()

# Типы для уровней логирования декораторов
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Допустимые имена уровней loguru для функции log_event.
# Используем строчные имена, чтобы их можно было напрямую вызывать как методы логгера.
EventLogLevel = Literal["trace", "debug", "info", "success", "warning", "error", "critical"]

# Глубина стека кадров, необходимая для корректного определения модуля‑вызывателя
# во вспомогательной функции _get_caller_module_name.
CALLER_FRAME_DEPTH = 3


_MIN_SECRET_LENGTH = 16
_MASKED_VALUE = "****"


class LoguruHandler(logging.Handler):
    """Адаптер для использования Loguru в стандартном logging.

    Позволяет перенаправлять логи из стандартного модуля logging
    в систему логирования Loguru.
    """

    def emit(self, record: logging.LogRecord) -> None:  # noqa: PLR6301
        """Обрабатывает запись лога и перенаправляет её в Loguru.

        Args:
            record: Запись лога из стандартного модуля logging.
        """
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            # Если levelname не распознан, используем числовой уровень
            level_int = record.levelno
            # Преобразуем в строку для loguru (используем константы logging)
            if level_int >= logging.CRITICAL:  # 50
                level = "CRITICAL"
            elif level_int >= logging.ERROR:  # 40
                level = "ERROR"
            elif level_int >= logging.WARNING:  # 30
                level = "WARNING"
            elif level_int >= logging.INFO:  # 20
                level = "INFO"
            elif level_int >= logging.DEBUG:  # 10
                level = "DEBUG"
            else:
                level = "TRACE"

        frame: FrameType | None = sys._getframe(6)
        depth = 6
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _get_known_secret_values() -> list[str]:
    """Возвращает список известных секретных значений для маскировки.

    Собирает секретные значения из конфигурации (GigaChat authorization key,
    Redis password, Postgres password) для последующей маскировки в логах.

    Returns:
        Список секретных значений длиной не менее _MIN_SECRET_LENGTH.
        Короткие значения не включаются, чтобы избежать ложных совпадений.
    """
    secrets: list[str] = []

    try:
        # Используем Config
        if isinstance(config, Config):
            gigachat_key = config.gigachat.authorization_key
            redis_password = config.redis.password
            postgres_password = config.postgres.password
        else:
            gigachat_key = config.gigachat_authorization_key
            redis_password = config.redis_password
            postgres_password = config.postgres_password

        # Основной чувствительный секрет — authorization key GigaChat.
        if gigachat_key and len(gigachat_key) >= _MIN_SECRET_LENGTH:
            secrets.append(gigachat_key)

        # Добавляем пароль Redis для маскировки в логах
        if redis_password and len(redis_password) >= _MIN_SECRET_LENGTH:
            secrets.append(redis_password)

        # Добавляем пароль Postgres для маскировки в логах
        if postgres_password and len(postgres_password) >= _MIN_SECRET_LENGTH:
            secrets.append(postgres_password)
    except Exception:
        # При ошибке чтения конфигурации не изменяем поведение логирования.
        return []

    return secrets


def mask_secrets(text: str) -> str:
    """Маскирует известные секретные значения в строке.

    Заменяет все вхождения секретных значений из _get_known_secret_values()
    на маску "****". Не использует regexp или эвристики по ключевым словам.

    Args:
        text: Текст для маскировки секретов.

    Returns:
        Текст с замаскированными секретами. Если произошла ошибка,
        возвращается исходный текст без изменений.
    """
    try:
        secrets = _get_known_secret_values()
        if not secrets or not text:
            return text

        result = text
        for value in secrets:
            if value and len(value) >= _MIN_SECRET_LENGTH:
                result = result.replace(value, _MASKED_VALUE)
        return result
    except Exception:
        # В случае любой ошибки не модифицируем исходный текст,
        # чтобы не ломать формат логов.
        logger.warning("mask_secrets: не удалось применить маскировку секретов (см. стек в debug)")
        logger.debug("mask_secrets: исключение при обработке текста", exc_info=True)
        return text


def setup_logger() -> None:
    """Настраивает систему логирования для приложения.

    Выполняет следующие действия:
    1. Удаляет стандартный обработчик loguru
    2. Настраивает JSON-логирование в stdout (обязательный sink)
    3. Опционально настраивает файловое логирование (если LOG_TO_FILE=true)
    4. Интегрирует логирование из uvicorn и prometheus_client

    Уровень логирования берётся из переменной окружения LOG_LEVEL
    или конфигурации (по умолчанию INFO).
    """

    # Удаляем стандартный обработчик loguru
    logger.remove()

    # Используем Config
    log_level = config.log_level

    # Основной sink: JSON в stdout (единственный обязательный sink)
    logger.add(
        sys.stdout,
        serialize=True,
        level=log_level,
        backtrace=False,  # Отключить для прода
        diagnose=False,  # Отключить для прода
        format="{message}",  # Минимальный формат, т.к. serialize=True
    )

    # Опциональный файловый sink для debug/forensics
    log_to_file = os.getenv("LOG_TO_FILE", "0").lower() in {"1", "true", "yes"}

    if log_to_file:
        log_dir = LOGS_DIR
        log_dir.mkdir(exist_ok=True)

        # Текстовый файл для человеко-читаемости
        logger.add(
            log_dir / "wednesday_bot.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            backtrace=True,  # Включить для файлов
            diagnose=True,  # Включить для файлов
        )

        # JSON файл для forensics (если нужен)
        logger.add(
            log_dir / "wednesday_bot.events.jsonl",
            serialize=True,
            level=log_level,
            rotation="10 MB",
            retention="7 days",
            compression="zip",
        )

    # Точечная интеграция сторонних логеров
    # НЕ трогаем root logger - это опасно и может создать рекурсию

    import logging

    # Интегрируем только uvicorn logger
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = [LoguruHandler()]
    uvicorn_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    uvicorn_logger.propagate = False  # Отключить propagate для избежания дублирования

    # Интегрируем prometheus_client logger
    prometheus_logger = logging.getLogger("prometheus_client")
    prometheus_logger.handlers = [LoguruHandler()]
    prometheus_logger.setLevel(logging.WARNING)  # Prometheus обычно на WARNING
    prometheus_logger.propagate = False

    # НЕ трогаем root logger!
    # Если библиотека логирует до setup_logger - это нормально, пусть идёт в stderr

    # Логируем успешную инициализацию
    if log_to_file:
        logger.info(f"Система логирования настроена, логи пишутся в stdout и {LOGS_DIR}")
    else:
        logger.info("Система логирования настроена, логи пишутся только в stdout (JSON)")


class LoguruLogger:
    """Адаптер loguru логгера, реализующий протокол ILogger.

    Все методы логирования вызывают log_event для гарантии очистки данных.
    """

    def __init__(self, loguru_logger: "LoggerType", module_name: str | None = None) -> None:
        """Инициализирует LoguruLogger.

        Args:
            loguru_logger: Экземпляр loguru.logger.
            module_name: Имя модуля для логирования.
        """
        self._logger = loguru_logger
        self._module_name = module_name
        self._bound_context: dict[str, Any] = {}

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне TRACE."""
        self._log("trace", message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне DEBUG."""
        self._log("debug", message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне INFO."""
        self._log("info", message, *args, **kwargs)

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне SUCCESS."""
        self._log("success", message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне WARNING."""
        self._log("warning", message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне ERROR."""
        self._log("error", message, *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне CRITICAL."""
        self._log("critical", message, *args, **kwargs)

    def bind(self, **kwargs: Any) -> "ILogger":  # noqa: ANN401
        """Создает новый экземпляр логгера с привязанным контекстом.

        Args:
            **kwargs: Контекстные данные для привязки ко всем последующим логам.

        Returns:
            Новый экземпляр LoguruLogger с обновленным контекстом.
        """
        new_context = {**self._bound_context, **kwargs}
        new_logger = LoguruLogger(self._logger, self._module_name)
        new_logger._bound_context = new_context
        return new_logger

    def add(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Добавляет sink к внутреннему loguru.logger.

        Этот метод доступен только в LoguruLogger и не является частью протокола ILogger.
        Используется для настройки логгера (например, в тестах).

        Args:
            *args: Аргументы для loguru.logger.add().
            **kwargs: Именованные аргументы для loguru.logger.add().

        Returns:
            ID добавленного sink.
        """
        return self._logger.add(*args, **kwargs)

    def _log(self, level: EventLogLevel, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Внутренний метод логирования.

        Упрощённый вариант:
        - Форматирует сообщение (если переданы args)
        - Собирает структурированный payload (event, user_id, status и т.п.)
        - Маскирует секреты и очищает payload
        - Делегирует непосредственно во внутренний loguru.logger
        """
        # 1. Форматирование сообщения
        if args:
            try:
                formatted_message = message.format(*args)
            except (ValueError, IndexError, KeyError):
                formatted_message = message
        else:
            formatted_message = message

        # 2. Объединяем привязанный контекст с переданными kwargs
        all_kwargs = {**self._bound_context, **kwargs}

        # Специальные структурированные поля
        user_id = all_kwargs.pop("user_id", None)
        prompt_hash = all_kwargs.pop("prompt_hash", None)
        image_id = all_kwargs.pop("image_id", None)
        latency_ms = all_kwargs.pop("latency_ms", None)
        status = all_kwargs.pop("status", None)
        event = all_kwargs.pop("event", formatted_message)
        exc_info = all_kwargs.pop("exc_info", None)

        # 3. Собираем payload в едином формате
        payload: dict[str, Any] = {
            "event": event,
            "service": os.getenv("SERVICE_NAME", "wednesday-bot"),
            "env": os.getenv("ENV", "dev"),
        }
        if user_id is not None:
            payload["user_id"] = str(user_id)
        if prompt_hash is not None:
            payload["prompt_hash"] = prompt_hash
        if image_id is not None:
            payload["image_id"] = image_id
        if latency_ms is not None:
            payload["latency_ms"] = float(latency_ms)
        if status is not None:
            payload["status"] = status

        # Остальные ключи считаем частью extra и также добавляем в payload
        if all_kwargs:
            for key, value in all_kwargs.items():
                if value is not None:
                    payload[key] = value

        # 4. Маскируем секреты
        masked_message = mask_secrets(formatted_message)
        scrubbed_obj = scrub(payload)
        if isinstance(scrubbed_obj, dict):
            scrubbed_payload = scrubbed_obj
        else:  # защитный fallback
            scrubbed_payload = payload

        # 5. Определяем базовый loguru.logger с учётом module_name
        base_logger = self._logger
        if self._module_name:
            base_logger = base_logger.bind(name=self._module_name)

        # Привязываем payload к логгеру
        bound_logger = base_logger.bind(**scrubbed_payload)

        # 6. Вызываем соответствующий метод loguru
        log_method = getattr(bound_logger, level, bound_logger.info)
        if exc_info is not None:
            log_method(masked_message, exc_info=exc_info)
        else:
            log_method(masked_message)


def get_logger(name: str | None = None) -> "ILogger":
    """
    Получает настроенный логгер для указанного модуля.

    Args:
        name: Имя модуля (обычно __name__)

    Returns:
        Настроенный экземпляр логгера, реализующий протокол ILogger
    """
    return LoguruLogger(logger, module_name=name)


def _get_caller_module_name() -> str | None:
    """Возвращает имя модуля, вызвавшего вспомогательную функцию логирования.

    Используется для того, чтобы log_event логировал события "от имени"
    реального модуля (bot.handlers, services.image_generator и т.д.),
    а не только модуля utils.logger.

    Returns:
        Имя модуля вызывающего кода или None, если не удалось определить.
    """
    frame = inspect.currentframe()
    if frame is None:  # pragma: no cover - защитный фоллбек
        return None
    # Стек:
    # 0 — _get_caller_module_name
    # 1 — log_event
    # 2 — фактическое место вызова log_event в коде бота
    outer_frames = inspect.getouterframes(frame, CALLER_FRAME_DEPTH)
    if len(outer_frames) < CALLER_FRAME_DEPTH:  # pragma: no cover - защитный фоллбек
        return None
    caller_frame = outer_frames[2].frame
    module_name = caller_frame.f_globals.get("__name__")
    return str(module_name) if isinstance(module_name, str) else None


_SENSITIVE_KEYWORDS: set[str] = {
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "authorization",
    "bearer",
    "access_token",
    "refresh_token",
    "apikey",
    "cookie",
    "set-cookie",
    "client_secret",
    "private_key",
    "secret_key",
}


def scrub(obj: object) -> object:
    """Рекурсивно очищает структурированные данные от секретов.

    Правила обработки:
    - dict: ключи, содержащие чувствительные слова, заменяют значение на "****";
      для остальных значений рекурсивно вызывается scrub.
    - list/tuple/set: рекурсивно применяет scrub к элементам.
    - str: пропускает через mask_secrets.
    - остальные типы возвращает как есть.

    Args:
        obj: Объект для очистки (dict, list, tuple, set, str или другой тип).

    Returns:
        Очищенный объект того же типа. При ошибке возвращает исходный объект.
    """
    try:
        if isinstance(obj, dict):
            cleaned: dict[object, object] = {}
            for key, value in obj.items():
                key_lower = str(key).lower()
                if any(word in key_lower for word in _SENSITIVE_KEYWORDS):
                    cleaned[key] = _MASKED_VALUE
                elif isinstance(value, dict | list | tuple | set | str):
                    cleaned[key] = scrub(value)
                else:
                    cleaned[key] = value
            return cleaned

        if isinstance(obj, list | tuple | set):
            container_type = type(obj)
            cleaned_items = [scrub(item) if isinstance(item, dict | list | tuple | set | str) else item for item in obj]
            return container_type(cleaned_items)

        if isinstance(obj, str):
            return mask_secrets(obj)

        return obj
    except Exception:
        # В защитном режиме возвращаем объект как есть, чтобы не ломать логи.
        logger.warning("scrub: не удалось обработать объект (см. стек в debug)")
        logger.debug("scrub: исключение при обработке объекта", exc_info=True)
        return obj


def log_event(  # noqa: PLR0913
    event: str,
    *,
    user_id: str | int | None = None,
    prompt_hash: str | None = None,
    image_id: str | None = None,
    latency_ms: int | float | None = None,
    status: str | None = None,
    extra: dict[str, Any] | None = None,
    level: EventLogLevel = "info",
    message: str | None = None,
    exc_info: bool | BaseException | tuple[type[BaseException], BaseException, Any] | None = None,
) -> None:
    """Высокоуровневая обёртка для структурированного логирования событий.

    Упрощённый вариант:
    - Выбирает логгер через get_logger()
    - Передаёт структурированные поля как kwargs в методы ILogger
    - Маскировка и scrub выполняются внутри LoguruLogger._log()
    """
    # Определяем модуль вызывающего кода
    caller_module = _get_caller_module_name()
    logger_instance = get_logger(caller_module or __name__)

    # Собираем kwargs для ILogger
    log_kwargs: dict[str, Any] = {
        "event": event,
        "user_id": user_id,
        "prompt_hash": prompt_hash,
        "image_id": image_id,
        "latency_ms": latency_ms,
        "status": status,
        "exc_info": exc_info,
    }
    if extra:
        log_kwargs.update(extra)

    # Выбираем метод по уровню и логируем
    log_method = getattr(logger_instance, level)
    log_method(message or event, **log_kwargs)


# HTTP статус код для разделения успешных и ошибочных запросов
_HTTP_STATUS_OK_MAX = 399


def log_http(
    method: str,
    path: str,
    status_code: int,
    latency_ms: float,
    *,
    level: EventLogLevel = "info",
) -> None:
    """Логирует HTTP-запрос с метриками.

    Args:
        method: HTTP-метод запроса (GET, POST и т.д.).
        path: Путь запроса.
        status_code: HTTP-статус код ответа.
        latency_ms: Латентность запроса в миллисекундах.
        level: Уровень логирования (по умолчанию "info").
    """
    log_event(
        event="http_request",
        status="ok" if status_code <= _HTTP_STATUS_OK_MAX else "error",
        latency_ms=latency_ms,
        extra={
            "method": method,
            "path": path,
            "status_code": status_code,
        },
        level=level,
        message=f"{method} {path} {status_code}",
    )


def log_worker(  # noqa: PLR0913
    task_name: str,
    task_id: str,
    status: str,
    latency_ms: float | None = None,
    *,
    level: EventLogLevel = "info",
    extra: dict[str, Any] | None = None,
) -> None:
    """Логирует событие выполнения Celery задачи.

    Args:
        task_name: Имя задачи Celery.
        task_id: Уникальный идентификатор задачи.
        status: Статус выполнения задачи (например, "started", "success", "failed").
        latency_ms: Время выполнения задачи в миллисекундах (опционально).
        level: Уровень логирования (по умолчанию "info").
        extra: Дополнительные поля для логирования (опционально).
    """
    worker_extra = {
        "task_name": task_name,
        "task_id": task_id,
        **(extra or {}),
    }
    log_event(
        event="celery_task",
        status=status,
        latency_ms=latency_ms,
        extra=worker_extra,
        level=level,
        message=f"Task {task_name} ({task_id}) {status}",
    )


P = ParamSpec("P")
R = TypeVar("R")
F = TypeVar("F", bound=Callable[..., Any])
MAX_ARG_REPR_LENGTH = 300


def _safe_repr(value: object) -> str:
    try:
        text = repr(value)
    except Exception as repr_error:  # pragma: no cover - fallback для нестандартных объектов
        text = f"<repr_error: {repr_error}>"
    if len(text) > MAX_ARG_REPR_LENGTH:
        return f"{text[:MAX_ARG_REPR_LENGTH]}..."
    return text


def _prepare_arguments(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    skip_first: bool,
) -> tuple[list[str], dict[str, str]]:
    args_repr = list(args)
    if skip_first and args_repr:
        args_repr = args_repr[1:]
    # Для позиционных аргументов оставляем только усечённый repr без
    # дополнительной фильтрации: секреты как позиционные параметры в
    # проекте не передаются, а логирование здесь нужно для отладки.
    args_repr_str = [_safe_repr(arg) for arg in args_repr]
    # Для именованных аргументов дополнительно защищаем потенциально
    # чувствительные данные (токены, пароли, ключи и т.п.). Это позволяет
    # безопасно использовать декоратор log_execution даже для функций,
    # которые принимают секреты через kwargs.
    kwargs_repr_str: dict[str, str] = {}
    for key, value in kwargs.items():
        key_lower = key.lower()
        if any(word in key_lower for word in _SENSITIVE_KEYWORDS):
            kwargs_repr_str[key] = "<redacted>"
        else:
            kwargs_repr_str[key] = _safe_repr(value)
    return args_repr_str, kwargs_repr_str


@overload
def log_execution(
    func: F,
    *,
    level: LogLevel = ...,
    log_args: bool = ...,
    log_result: bool = ...,
) -> F: ...


@overload
def log_execution(
    func: None = None,
    *,
    level: LogLevel = ...,
    log_args: bool = ...,
    log_result: bool = ...,
) -> Callable[[F], F]: ...


def log_execution(
    func: F | None = None,
    *,
    level: LogLevel = "INFO",
    log_args: bool = True,
    log_result: bool = False,
) -> F | Callable[[F], F]:
    """
    Декоратор, автоматически логирующий начало, успешное завершение и ошибки функции/метода.
    Поддерживает как синхронные, так и асинхронные функции.

    Args:
        func: Функция для обёртки (при использовании как декоратор без скобок)
        level: Уровень логирования для начала и завершения (DEBUG, INFO, WARNING, ERROR)
        log_args: Логировать ли аргументы функции (по умолчанию True)
        log_result: Логировать ли результат функции (по умолчанию False)

    Returns:
        Обёрнутая функция с логированием
    """
    # Поддержка использования как @log_execution или @log_execution(level="DEBUG")
    if func is None:
        # Вызов с параметрами: @log_execution(level="DEBUG")
        def decorator(f: F) -> F:
            return log_execution(f, level=level, log_args=log_args, log_result=log_result)

        return decorator

    if getattr(func, "__log_wrapped__", False):
        return func

    func_name = f"{func.__module__}.{func.__qualname__}"
    parameters = list(inspect.signature(func).parameters.keys())
    skip_first_argument = bool(parameters and parameters[0] in {"self", "cls"})

    # Определяем, является ли метод приватным (начинается с _)
    # Для приватных методов используем DEBUG, если уровень не был явно указан (остался INFO по умолчанию)
    is_private = func.__name__.startswith("_") and not func.__name__.startswith("__")
    # Если уровень явно указан (не INFO по умолчанию), используем его; иначе для приватных используем DEBUG
    effective_level: LogLevel = "DEBUG" if (is_private and level == "INFO") else level

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            logger_instance = get_logger(func.__module__)
            # Получаем метод логирования по уровню из logger_instance
            log_method = getattr(logger_instance, effective_level.lower())
            if log_args:
                args_repr, kwargs_repr = _prepare_arguments(args, kwargs, skip_first=skip_first_argument)
                log_method(f"Начало {func_name} args={args_repr} kwargs={kwargs_repr}")
            else:
                log_method(f"Начало {func_name}")
            try:
                result = await func(*args, **kwargs)
                if log_result:
                    log_method(f"Успешное завершение {func_name} result={_safe_repr(result)}")
                else:
                    log_method(f"Успешное завершение {func_name}")
                return result
            except Exception as exc:
                logger_instance.error(f"Ошибка в {func_name}: {exc}", exc_info=True)
                raise

        setattr(async_wrapper, "__log_wrapped__", True)  # noqa: B010
        return cast(F, async_wrapper)

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        logger_instance = get_logger(func.__module__)
        # Получаем метод логирования по уровню из logger_instance
        log_method = getattr(logger_instance, effective_level.lower())
        if log_args:
            args_repr, kwargs_repr = _prepare_arguments(args, kwargs, skip_first=skip_first_argument)
            log_method(f"Начало {func_name} args={args_repr} kwargs={kwargs_repr}")
        else:
            log_method(f"Начало {func_name}")
        try:
            result = func(*args, **kwargs)
            if log_result:
                log_method(f"Успешное завершение {func_name} result={_safe_repr(result)}")
            else:
                log_method(f"Успешное завершение {func_name}")
            return result
        except Exception as exc:
            logger_instance.error(f"Ошибка в {func_name}: {exc}", exc_info=True)
            raise

    setattr(sync_wrapper, "__log_wrapped__", True)  # noqa: B010
    return cast(F, sync_wrapper)


def log_all_methods(
    *,
    skip: tuple[str, ...] | None = None,
    skip_private: bool = True,
    default_level: LogLevel = "INFO",
    method_levels: dict[str, LogLevel] | None = None,
) -> Callable[[type], type]:
    """
    Класс-декоратор, автоматически оборачивающий все методы класса в log_execution.

    Args:
        skip: Список имен методов, которые не нужно оборачивать (полное исключение).
        skip_private: Исключать ли приватные методы (начинающиеся с `_`, но не `__`).
                     По умолчанию True - приватные методы не логируются.
        default_level: Уровень логирования по умолчанию для публичных методов (INFO, DEBUG, WARNING, ERROR).
        method_levels: Словарь {имя_метода: уровень} для явного указания уровня логирования
                      для конкретных методов. Имеет приоритет над default_level.

    Примеры:
        @log_all_methods()  # Логирует только публичные методы на уровне INFO
        @log_all_methods(skip_private=False)  # Логирует все методы, приватные на DEBUG
        @log_all_methods(skip=("_internal",), method_levels={"critical_method": "ERROR"})
    """

    skip_set = set(skip or ())
    method_levels_dict = method_levels or {}

    def decorator(cls: type) -> type:
        for attr_name, attr_value in cls.__dict__.items():
            # Пропускаем явно исключённые методы
            if attr_name in skip_set:
                continue

            # Пропускаем магические методы (__init__, __str__ и т.д.)
            if attr_name.startswith("__") and attr_name.endswith("__"):
                continue

            # Пропускаем приватные методы, если skip_private=True
            is_private = attr_name.startswith("_") and not attr_name.startswith("__")
            if skip_private and is_private:
                continue

            # Определяем уровень логирования для метода
            level = method_levels_dict.get(attr_name, default_level)
            # Для приватных методов, если не указан явно, используем DEBUG
            if is_private and attr_name not in method_levels_dict:
                level = "DEBUG"

            # Оборачиваем функцию/метод
            if inspect.isfunction(attr_value):
                setattr(cls, attr_name, log_execution(attr_value, level=level))
            elif isinstance(attr_value, staticmethod):
                func = getattr(attr_value, "__func__", None)
                if func is not None:
                    wrapped = log_execution(func, level=level)
                    setattr(cls, attr_name, staticmethod(wrapped))
            elif isinstance(attr_value, classmethod):
                func = getattr(attr_value, "__func__", None)
                if func is not None:
                    wrapped = log_execution(func, level=level)
                    setattr(cls, attr_name, classmethod(wrapped))
        return cls

    return decorator


# Инициализируем логирование при импорте модуля
setup_logger()
