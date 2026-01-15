"""Application service для классификации типов ошибок.

Инкапсулирует логику определения типов ошибок (сетевые, критические, неожиданные),
соблюдая границы слоёв.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    pass


class ErrorClassificationService(BaseService):
    """Сервис для классификации типов ошибок.

    Инкапсулирует логику определения типов ошибок для правильной обработки.
    """

    def __init__(
        self,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис классификации ошибок.

        Args:
            logger: Экземпляр логгера.
        """
        super().__init__(logger)

    @staticmethod
    def is_telegram_error(
        error: Exception,
    ) -> bool:
        """Проверяет, является ли ошибка сетевой ошибкой Telegram API.

        Args:
            error: Исключение для проверки.

        Returns:
            True если ошибка является TelegramError, NetworkError или TimedOut, False иначе.
        """
        from telegram.error import NetworkError, TelegramError, TimedOut

        return isinstance(error, TelegramError | NetworkError | TimedOut)

    @staticmethod
    def is_critical_error(
        error: Exception,
    ) -> bool:
        """Проверяет, является ли ошибка критической системной ошибкой.

        Критические ошибки должны пробрасываться выше без обработки.

        Args:
            error: Исключение для проверки.

        Returns:
            True если ошибка является критической (KeyboardInterrupt, SystemExit,
            MemoryError, SystemError), False иначе.
        """
        return isinstance(error, KeyboardInterrupt | SystemExit | MemoryError | SystemError)

    def classify_error_type(
        self,
        error: Exception,
        context: str = "операции",
    ) -> tuple[bool, bool]:
        """Классифицирует тип ошибки.

        Args:
            error: Исключение для классификации.
            context: Контекст операции для логирования.

        Returns:
            Кортеж (is_telegram_error, is_critical_error).
        """
        is_telegram = self.is_telegram_error(error)
        is_critical = self.is_critical_error(error)
        return is_telegram, is_critical
