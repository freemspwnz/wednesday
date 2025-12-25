"""Обработчик ошибок для PTB хендлеров."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.ext import ContextTypes

from infra.logging.logger import get_logger, log_event
from shared.protocols import ILogger

if TYPE_CHECKING:
    pass


class BotErrorHandler:
    """Глобальный обработчик ошибок PTB.

    Централизованный обработчик всех необработанных исключений из обработчиков
    команд и сообщений. Обеспечивает логирование, отправку в Sentry (если включен)
    и структурированное логирование для дальнейшего анализа.
    """

    def __init__(self, logger: ILogger | None = None) -> None:
        """Инициализирует обработчик ошибок.

        Args:
            logger: Экземпляр логгера. Если None, создается новый.
        """
        self.logger = logger or get_logger(__name__)

    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обрабатывает необработанные исключения из хендлеров PTB.

        Args:
            update: Объект обновления Telegram, которое вызвало ошибку
                (может быть любого типа в зависимости от события).
            context: Контекст бота, содержащий информацию об ошибке через
                context.error и другие метаданные.

        Side Effects:
            - Логирует ошибку с полным стеком через logger.error().
            - Отправляет исключение в Sentry через sentry_sdk.capture_exception()
              (если SDK инициализирован).
            - Записывает структурированное событие через log_event() для анализа.
        """
        error = getattr(context, "error", None)
        self.logger.error(f"Необработанное исключение в обработчике PTB: {error!r}", exc_info=True)

        # Отправляем исключение в Sentry, если SDK инициализирован.
        if error is not None:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(error)
            except Exception:
                # Ошибки в интеграции Sentry не должны ломать основной поток.
                pass

        # Логируем структурированное событие для унифицированного JSON‑логирования.
        try:
            log_event(
                event="unhandled_exception",
                status="error",
                extra={
                    "where": "ptb_error_handler",
                    "error": repr(error),
                    "update_repr": repr(update),
                },
                level="error",
                message="Необработанное исключение в обработчике PTB",
            )
        except Exception:
            # Любые ошибки логирования здесь игнорируем, чтобы не усугублять ситуацию.
            pass
