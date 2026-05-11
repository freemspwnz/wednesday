import logging

from loguru import logger

# Глобальные переменные для маскировки
_MASKED_VALUE = "****"
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


def scrub(obj: str | dict | list | tuple | set, secrets: list[str] | None = None) -> str | dict | list | tuple | set:
    """Рекурсивно очищает данные и маскирует известные секреты."""
    if isinstance(obj, str):
        if secrets:
            for s in secrets:
                if s:
                    obj = obj.replace(s, _MASKED_VALUE)
        return obj

    if isinstance(obj, dict):
        return {
            k: (_MASKED_VALUE if any(w in str(k).lower() for w in _SENSITIVE_KEYWORDS) else scrub(v, secrets))
            for k, v in obj.items()
        }

    if isinstance(obj, list | tuple | set):
        return type(obj)([scrub(i, secrets) for i in obj])

    return obj


class LoguruHandler(logging.Handler):
    """Адаптер для использования Loguru в стандартном logging."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: PLR6301
        # Получаем уровень из loguru, если он там есть
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Находим кадр стека, откуда пришло сообщение
        frame, depth = logging.currentframe(), 2
        if frame is not None:
            while frame.f_code.co_filename == logging.__file__:
                parent = frame.f_back
                if parent is None:
                    break
                frame = parent
                depth += 1

        # Передаем в loguru с сохранением оригинального имени логгера библиотеки
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage(), logger_name=record.name)
