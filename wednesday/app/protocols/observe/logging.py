from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ILogger(Protocol):
    """Протокол для системы логирования."""

    def trace(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне TRACE.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне DEBUG.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне INFO.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне SUCCESS.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне WARNING.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне ERROR.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне CRITICAL.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на уровне EXCEPTION.

        Args:
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def log(self, level: str, message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Логирует сообщение на указанном уровне.

        Args:
            level: Уровень логирования.
            message: Сообщение для логирования (может содержать {} для форматирования).
            *args: Аргументы для форматирования сообщения.
            **kwargs: Дополнительный контекст для логирования.
        """
        ...

    def bind(self, **kwargs: Any) -> ILogger:  # noqa: ANN401
        """Создает новый экземпляр логгера с привязанным контекстом.

        Args:
            **kwargs: Контекстные данные для привязки ко всем последующим логам.

        Returns:
            Новый экземпляр ILogger с обновленным контекстом.
        """
        ...
