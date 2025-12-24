"""Базовый класс для всех сервисов."""

from __future__ import annotations

import traceback
from typing import Any, TypeVar

from shared.base.exceptions import UnexpectedAppError
from shared.protocols import ILogger

T = TypeVar("T", bound=UnexpectedAppError)


class BaseService:
    """Базовый класс для всех сервисов.

    Предоставляет общую функциональность:
    - Логирование через self.logger (инъекция зависимости через протокол ILogger)
    - Единообразная обработка неожиданных ошибок
    """

    def __init__(self, logger: ILogger) -> None:
        """Инициализирует базовый сервис.

        Args:
            logger: Экземпляр логгера, реализующий протокол ILogger.
        """
        self.logger = logger.bind(service=self.__class__.__name__)

    def handle_unexpected_error(
        self,
        error: BaseException,
        error_type: type[T],
        message: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Обрабатывает неожиданную ошибку единообразно.

        Создает обёртку для неожиданной ошибки, логирует её с полным контекстом
        и возвращает обёрнутое исключение для проброса.

        **Важно:** Системные ошибки (MemoryError, SystemExit, KeyboardInterrupt)
        должны обрабатываться отдельно и пробрасываться выше без обёртки.

        Args:
            error: Оригинальное исключение, которое нужно обернуть.
            error_type: Тип исключения для создания (UnexpectedDispatchError, UnexpectedImageError и т.д.).
            message: Кастомное сообщение об ошибке. Если не указано, используется стандартное.
            context: Дополнительный контекст для логирования (chat_id, user_id, api и т.д.).

        Returns:
            Обёрнутое исключение указанного типа, готовое для проброса.

        Raises:
            MemoryError, SystemExit, KeyboardInterrupt: Системные ошибки пробрасываются без обёртки.

        Example:
            ```python
            try:
                # какой-то код
            except (ImageGenerationError, StorageError, CacheError) as e:
                # Обработка ожидаемых ошибок
                ...
            except (MemoryError, SystemExit, KeyboardInterrupt) as e:
                # Пробрасываем системные ошибки выше
                raise
            except BaseException as e:
                # Только для действительно неожиданных ошибок
                error = self.handle_unexpected_error(
                    e,
                    UnexpectedDispatchError,
                    message=f"Ошибка при отправке в чат {chat_id}",
                    context={"chat_id": chat_id, "slot_date": slot_date}
                )
                raise error from e
            ```
        """
        # Системные ошибки должны пробрасываться без обёртки
        if isinstance(error, MemoryError | SystemExit | KeyboardInterrupt):
            raise error

        error_message = message or f"Unexpected error: {error}"
        unexpected_error = error_type(
            error_message,
            original_error=error,
        )

        log_data: dict[str, Any] = {
            "event": "unexpected_error",
            "status": "error",
            "error_type": type(unexpected_error).__name__,
            "error_message": str(unexpected_error),
            "traceback": traceback.format_exc(),
        }

        if context:
            log_data.update(context)

        self.logger.error(
            f"Неожиданная ошибка: {unexpected_error}",
            **log_data,
        )

        return unexpected_error

    def _safe_log_error(
        self,
        message: str,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Безопасно логирует ошибку, не скрывая оригинальное исключение.

        Используется для логирования ошибок внутри транзакций или других критичных блоков,
        где сбой логирования не должен скрывать оригинальную ошибку.

        Args:
            message: Сообщение для логирования.
            error: Исключение, которое нужно залогировать.
            context: Дополнительный контекст для логирования.

        Note:
            Если логирование само вызовет исключение, оно будет проигнорировано,
            чтобы не скрыть оригинальную ошибку.
        """
        try:
            import traceback

            log_data: dict[str, Any] = {
                "event": "error",
                "status": "error",
                "error_type": type(error).__name__,
                "error_message": str(error),
                "traceback": traceback.format_exc(),
            }

            if context:
                log_data.update(context)

            self.logger.error(message, **log_data)
        except (MemoryError, SystemExit, KeyboardInterrupt):
            # Системные ошибки при логировании пробрасываем выше
            # (хотя это крайне маловероятно)
            raise
        except BaseException:
            # Игнорируем любые другие ошибки логирования,
            # чтобы не скрыть оригинальную ошибку транзакции
            # В критических случаях можно добавить fallback логирование
            pass
