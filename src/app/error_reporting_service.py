"""Application service для отправки ошибок в системы мониторинга.

Инкапсулирует логику отправки ошибок в Sentry и классификации ошибок,
соблюдая границы слоёв.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.error_classification_service import ErrorClassificationService
from shared.base.base_service import BaseService
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    pass


class ErrorReportingService(BaseService):
    """Сервис для отправки ошибок в системы мониторинга.

    Инкапсулирует логику отправки ошибок в Sentry и классификации ошибок.
    """

    def __init__(
        self,
        error_classification_service: ErrorClassificationService,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис отправки ошибок.

        Args:
            error_classification_service: Сервис для классификации типов ошибок.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._error_classification = error_classification_service

    def report_error_to_sentry(
        self,
        error: Exception | None,
    ) -> None:
        """Отправляет ошибку в Sentry, если SDK инициализирован.

        Args:
            error: Исключение для отправки в Sentry.
        """
        if error is None:
            return

        try:
            import sentry_sdk

            sentry_sdk.capture_exception(error)
        except Exception as sentry_error:
            # Ошибки в интеграции Sentry не должны ломать основной поток.
            # Но логируем для диагностики проблем с мониторингом
            self.logger.warning(f"Ошибка при отправке в Sentry: {sentry_error}", exc_info=False)

    def classify_error(
        self,
        error: Exception,
    ) -> dict[str, bool]:
        """Классифицирует ошибку по типам.

        Args:
            error: Исключение для классификации.

        Returns:
            Словарь с флагами классификации: is_telegram_error, is_critical_error.
        """
        is_telegram = self._error_classification.is_telegram_error(error)
        is_critical = self._error_classification.is_critical_error(error)
        return {
            "is_telegram_error": is_telegram,
            "is_critical_error": is_critical,
        }
