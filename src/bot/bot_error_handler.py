"""Обработчик ошибок для PTB хендлеров."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from telegram.ext import ContextTypes

from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    pass


class BotErrorHandler:
    """Глобальный обработчик ошибок PTB.

    Централизованный обработчик всех необработанных исключений из обработчиков
    команд и сообщений. Обеспечивает логирование, отправку в Sentry (если включен)
    и структурированное логирование для дальнейшего анализа.
    """

    def __init__(self, logger: ILogger) -> None:
        """Инициализирует обработчик ошибок.

        Args:
            logger: Экземпляр логгера для логирования ошибок.
        """
        self.logger = logger

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
            - Записывает структурированное событие через logger.error() с дополнительными полями для анализа.
        """
        error = getattr(context, "error", None)
        self.logger.error(f"Необработанное исключение в обработчике PTB: {error!r}", exc_info=True)

        # Отправляем исключение в Sentry, если SDK инициализирован.
        if error is not None:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(error)
            except Exception as sentry_error:
                # Ошибки в интеграции Sentry не должны ломать основной поток.
                # Но логируем для диагностики проблем с мониторингом
                self.logger.warning(f"Ошибка при отправке в Sentry: {sentry_error}", exc_info=False)

        # Логируем структурированное событие для унифицированного JSON‑логирования.
        # Используем ILogger протокол вместо прямого импорта из infra.logging.logger
        # для соблюдения архитектурных границ
        try:
            self.logger.error(
                "Необработанное исключение в обработчике PTB",
                event="unhandled_exception",
                status="error",
                where="ptb_error_handler",
                error=repr(error),
                update_repr=repr(update),
            )
        except Exception as log_error:
            # Критическая ошибка - не можем даже залогировать
            # Используем print как последний резерв (будет видно в stdout/stderr)
            print(
                f"КРИТИЧЕСКАЯ ОШИБКА: не удалось залогировать событие: {log_error}",
                file=sys.stderr,
            )
