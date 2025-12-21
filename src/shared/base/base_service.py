"""Базовый класс для всех сервисов."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infra.logging.logger import EventLogLevel, get_logger, log_event

if TYPE_CHECKING:
    from loguru import Logger


class BaseService:
    """Базовый класс для всех сервисов.

    Предоставляет общую функциональность:
    - Логирование через self.logger
    - Унифицированное логирование событий через log_event()
    """

    def __init__(self) -> None:
        """Инициализирует базовый сервис.

        Создаёт логгер с именем класса для удобного отслеживания.
        """
        self.logger: Logger = get_logger(self.__class__.__name__)

    def log_event(  # noqa: PLR0913, PLR6301
        self,
        event: str,
        *,
        user_id: str | int | None = None,
        prompt_hash: str | None = None,
        image_id: str | None = None,
        latency_ms: int | float | None = None,
        status: str | None = None,
        extra: dict[str, Any] | None = None,
        level: EventLogLevel = "info",
        message: str | None = None,
    ) -> None:
        """Унифицированное логирование событий сервиса.

        Args:
            event: Название события для логирования.
            user_id: ID пользователя (опционально).
            prompt_hash: Хэш промпта (опционально).
            image_id: ID изображения (опционально).
            latency_ms: Задержка в миллисекундах (опционально).
            status: Статус события (например, "success", "error", "in_progress).
            extra: Дополнительные поля для структурированного логирования.
            level: Уровень логирования (по умолчанию "info").
            message: Текстовое сообщение для логирования.
        """
        log_event(
            event=event,
            user_id=user_id,
            prompt_hash=prompt_hash,
            image_id=image_id,
            latency_ms=latency_ms,
            status=status,
            extra=extra,
            level=level,
            message=message,
        )
