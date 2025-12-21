"""Базовый класс для всех сервисов."""

from __future__ import annotations

from shared.protocols import ILogger


class BaseService:
    """Базовый класс для всех сервисов.

    Предоставляет общую функциональность:
    - Логирование через self.logger (инъекция зависимости через протокол ILogger)
    """

    def __init__(self, logger: ILogger) -> None:
        """Инициализирует базовый сервис.

        Args:
            logger: Экземпляр логгера, реализующий протокол ILogger.
        """
        self.logger = logger.bind(service=self.__class__.__name__)
