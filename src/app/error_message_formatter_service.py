"""Application service для форматирования сообщений об ошибках.

Инкапсулирует логику форматирования ошибок для пользовательских сообщений,
соблюдая границы слоёв и централизуя правила форматирования.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.base.exceptions import RepoError, ServiceError
from shared.protocols.infrastructure import ILogger


class ErrorMessageFormatterService(BaseService):
    """Сервис для форматирования сообщений об ошибках.

    Инкапсулирует логику форматирования ошибок для пользовательских сообщений,
    централизуя правила форматирования и соблюдая границы слоёв.
    """

    MAX_ERROR_MESSAGE_LENGTH = 200

    def __init__(
        self,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис форматирования ошибок.

        Args:
            logger: Экземпляр логгера.
        """
        super().__init__(logger)

    def format_service_error(self, error: ServiceError) -> str:
        """Форматирует ошибку сервиса для пользователя.

        Args:
            error: Исключение сервисного слоя.

        Returns:
            Отформатированное сообщение об ошибке для пользователя.
        """
        error_text = str(error)[: self.MAX_ERROR_MESSAGE_LENGTH]
        return f"❌ Ошибка сервиса: {error_text}"

    def format_repo_error(self, error: RepoError) -> str:
        """Форматирует ошибку репозитория для пользователя.

        Args:
            error: Исключение репозитория.

        Returns:
            Отформатированное сообщение об ошибке для пользователя.
        """
        error_text = str(error)[: self.MAX_ERROR_MESSAGE_LENGTH]
        return f"❌ Ошибка доступа к данным: {error_text}"

    @staticmethod
    def format_validation_error() -> str:
        """Форматирует сообщение об ошибке валидации.

        Returns:
            Отформатированное сообщение об ошибке валидации.
        """
        return "❌ Ошибка валидации данных"

    @staticmethod
    def format_network_error() -> str:
        """Форматирует сообщение о сетевой ошибке Telegram API.

        Returns:
            Отформатированное сообщение о сетевой ошибке.
        """
        return "❌ Временная проблема с Telegram API. Попробуйте позже."

    @staticmethod
    def format_timeout_error() -> str:
        """Форматирует сообщение об ошибке таймаута команды.

        Returns:
            Отформатированное сообщение об ошибке таймаута.
        """
        return "❌ Команда заняла слишком много времени. Попробуйте позже."
