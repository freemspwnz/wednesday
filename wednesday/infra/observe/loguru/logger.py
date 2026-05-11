from typing import Any

from loguru import logger

from app.exceptions import LogMessageFormatError
from app.protocols import Logger


class LoguruLogger(Logger):
    """Адаптер loguru логгера, реализующий протокол Logger."""

    __slots__ = ("_bound_context", "_core")

    def __init__(self, core: Any, bound_context: dict[str, Any] | None = None) -> None:  # noqa: ANN401
        self._core = core
        ctx: dict[str, Any] = dict(bound_context or {})
        if "module" not in ctx:
            ctx["module"] = "unknown"
        self._bound_context = ctx

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log("TRACE", message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log("DEBUG", message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log("INFO", message, *args, **kwargs)

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log("SUCCESS", message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log("WARNING", message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log("ERROR", message, *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log("CRITICAL", message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("exc_info", True)
        self._log("ERROR", message, *args, **kwargs)

    def log(self, level: str, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._log(level, message, *args, **kwargs)

    def bind(self, **kwargs: Any) -> Logger:  # noqa: ANN401
        """Создает новый экземпляр логгера с привязанным контекстом."""
        return LoguruLogger(
            self._core,
            bound_context={**self._bound_context, **kwargs},
        )

    def _log(self, level: str, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Основной метод маршрутизации логов."""
        # 1. Форматирование сообщения (стандартный подход python logging)
        if args:
            try:
                message = message.format(*args)
            except (ValueError, IndexError, KeyError) as e:
                raise LogMessageFormatError(message, args) from e

        # 2. Подготовка контекста (extra)
        # Объединяем контекст из bind() и текущие kwargs
        payload = {**self._bound_context, **kwargs}

        # Извлекаем спец. поля для структурированного логирования
        exc_info = payload.pop("exc_info", None)

        structured = {
            "user_id": payload.pop("user_id", None),
            "chat_id": payload.pop("chat_id", None),
            "generation_id": payload.pop("generation_id", None),
        }

        # 3. Передача в Loguru
        # Используем opt(depth=2), чтобы loguru правильно определил файл/линию вызова
        self._core.opt(depth=2, exception=exc_info).bind(**structured, **payload).log(level, message)


def get_logger(name: str | None = None) -> Logger:
    """Фабрика для получения типизированного логгера."""
    if name is None:
        return LoguruLogger(logger)
    return LoguruLogger(logger, bound_context={"module": name})
