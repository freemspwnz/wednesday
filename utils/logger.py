"""
Модуль настройки логирования для приложения.
Использует библиотеку loguru для удобного и красивого логирования.
"""

import inspect
import sys
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar, cast, overload

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger as LoggerType

from utils.config import config
from utils.paths import LOGS_CONTAINER_PATH, resolve_logs_dir

# Типы для уровней логирования декораторов
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Допустимые имена уровней loguru для функции log_event.
# Используем строчные имена, чтобы их можно было напрямую вызывать как методы логгера.
EventLogLevel = Literal["trace", "debug", "info", "success", "warning", "error", "critical"]

# Глубина стека кадров, необходимая для корректного определения модуля‑вызывателя
# во вспомогательной функции _get_caller_module_name.
CALLER_FRAME_DEPTH = 3


def setup_logger() -> None:
    """
    Настраивает систему логирования для приложения.

    Конфигурирует:
    - Уровень логирования из конфигурации
    - Формат сообщений с временными метками
    - Вывод в консоль и файл
    - Ротацию логов по размеру и времени
    """

    # Удаляем стандартный обработчик loguru
    logger.remove()

    # Создаем папку для логов, если её нет.
    # Используем относительный путь (logs/), который внутри Docker-контейнера
    # при WORKDIR=/app будет соответствовать /app/logs и будет примонтирован
    # в volume. При локальном запуске логи пишутся в ./logs рядом с проектом.
    log_dir = resolve_logs_dir()
    log_dir.mkdir(exist_ok=True)

    # Настраиваем вывод в консоль с цветами (читаемые текстовые логи для локальной разработки).
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>",
        level=config.log_level,
        colorize=True,
    )

    # Настраиваем вывод в файл с подробной информацией (человеко-читаемый формат).
    # Важно: путь привязан к volume с логами внутри контейнера:
    # - локально пишем в ./logs;
    # - в Docker при WORKDIR=/app это /app/logs, примонтированный как volume.
    # Используем ротацию по размеру (10 MB) и retention 7 дней, чтобы:
    # - не допустить бесконтрольного роста логов;
    # - сохранить достаточно истории для расследований инцидентов.
    logger.add(
        log_dir / "wednesday_bot.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=config.log_level,
        rotation="10 MB",  # Ротация по размеру файла
        retention="7 days",  # Хранить логи 7 дней
        compression="zip",  # Сжимать старые логи
        backtrace=True,  # Показывать полный стек ошибок
        diagnose=True,  # Показывать переменные в ошибках
    )

    # Дополнительный sink c JSON‑сериализацией (структурированные логи).
    #
    # В этом sink loguru сериализует запись в один JSON‑объект с полями:
    # - "time"    — timestamp события;
    # - "level"   — уровень логирования;
    # - "message" — строковое сообщение;
    # - а также всеми дополнительными полями, добавленными через logger.bind(...)
    #   (например, user_id, prompt_hash, image_id, latency_ms, status).
    #
    # Такой формат удобно парсить в Docker/CI, отдавать в централизованные системы
    # логирования (ELK, Loki и т.п.) и использовать для метрик и дашбордов.
    logger.add(
        sys.stdout,
        serialize=True,  # включаем JSON‑формат
        level=config.log_level,
        backtrace=True,
        diagnose=True,
    )

    # Логируем успешную инициализацию с явным указанием контейнерного пути.
    logger.info(
        f"Система логирования успешно настроена, логи пишутся в {LOGS_CONTAINER_PATH}",
    )


def get_logger(name: str | None = None) -> "LoggerType":
    """
    Получает настроенный логгер для указанного модуля.

    Args:
        name: Имя модуля (обычно __name__)

    Returns:
        Настроенный экземпляр логгера
    """
    if name:
        return logger.bind(name=name)
    return logger


def _get_caller_module_name() -> str | None:
    """
    Возвращает имя модуля, вызвавшего вспомогательную функцию логирования.

    Это нужно для того, чтобы log_event логировал события "от имени" реального
    модуля (bot.handlers, services.image_generator и т.д.), а не только
    модуля utils.logger. В логах и JSON‑записях поле `name` останется
    привычным и понятным.
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
) -> None:
    """
    Высокоуровневая обёртка для структурированного логирования событий.

    Функция:
    - собирает стандартные поля (event, user_id, prompt_hash, image_id,
      latency_ms, status);
    - объединяет их с дополнительными полями из `extra`;
    - отфильтровывает все значения None, чтобы в JSON не появлялись "пустые" ключи;
    - привязывает получившийся набор полей к логгеру через logger.bind(...);
    - вызывает нужный метод loguru (info, error, warning и др.) с указанным message.

    В результате в JSON‑логах (sink с serialize=True) появляется одна запись,
    где:
    - стандартные поля доступны как отдельные ключи;
    - дополнительные поля из extra находятся на том же уровне;
    - формат остаётся совместимым с парсерами структурированных логов.

    Args:
        event: Краткий тип/код события (например, "image_generation", "handler_error").
        user_id: Идентификатор пользователя (Telegram user id).
        prompt_hash: Хэш промпта (sha256, 64‑символьный hex).
        image_id: Идентификатор или hash изображения (может совпадать с image_hash из БД).
        latency_ms: Латентность операции в миллисекундах.
        status: Статус события ("ok", "error", "cached", "started" и т.п.).
        extra: Дополнительные произвольные поля, которые нужно добавить в лог.
        level: Уровень логирования loguru ("info", "error", "warning" и т.д.).
        message: Человеко‑читаемое сообщение; если не указано, используется event.
    """
    # Базовый набор полей события. Мы намеренно не включаем сюда None,
    # чтобы далее их можно было отфильтровать и не захламлять JSON.
    payload: dict[str, Any] = {"event": event}

    if user_id is not None:
        # user_id может быть int (Telegram id) или str — приводим к строке,
        # чтобы в JSON не было неоднородности типов.
        payload["user_id"] = str(user_id)
    if prompt_hash is not None:
        payload["prompt_hash"] = prompt_hash
    if image_id is not None:
        payload["image_id"] = image_id
    if latency_ms is not None:
        payload["latency_ms"] = float(latency_ms)
    if status is not None:
        payload["status"] = status

    # Дополнительные поля (если переданы) перекладываем поверх стандартных.
    # При совпадении ключей extra имеет приоритет — это даёт возможность
    # локально переопределить значение в конкретном кейсе.
    if extra:
        for key, value in extra.items():
            if value is not None:
                payload[key] = value

    # Получаем логгер с именем модуля вызывающего кода, чтобы:
    # - сохранить привычное поле `name` в логах;
    # - при этом "забиндить" к нему все дополнительные поля payload.
    caller_module = _get_caller_module_name()
    base_logger = get_logger(caller_module) if caller_module else get_logger(__name__)

    # bind(...) в loguru не записывает лог немедленно, а возвращает новый логгер,
    # у которого все указанные ключи будут автоматически добавляться к каждой записи.
    # Эти ключи:
    # - выводятся в текстовом формате (если включим {extra[...]});
    # - попадают как отдельные поля в JSON‑sink (serialize=True), что и нужно
    #   для структурированных логов.
    bound_logger = base_logger.bind(**payload)

    # Выбираем метод логирования по имени уровня. Если по какой‑то причине
    # передан неподдерживаемый level, по умолчанию используем info.
    log_method = getattr(bound_logger, level, bound_logger.info)

    # Текстовое сообщение, которое увидит разработчик в консоли/файле.
    # В JSON оно попадает в поле "message".
    text = message or event
    log_method(text)


P = ParamSpec("P")
R = TypeVar("R")
F = TypeVar("F", bound=Callable[..., Any])
MAX_ARG_REPR_LENGTH = 300
_SENSITIVE_KEYWORDS: set[str] = {
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "authorization",
}


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
