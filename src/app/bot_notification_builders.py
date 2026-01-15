"""Билдеры для форматирования сообщений бота пользователям.

Инкапсулирует логику форматирования сообщений для команд бота,
обеспечивая единообразное представление информации и соблюдение границ слоёв.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.admin_command_service import CommandResult


class BotNotificationBuilders:
    """Билдеры для форматирования сообщений бота пользователям.

    Инкапсулирует логику форматирования сообщений для команд бота,
    обеспечивая единообразное представление информации.
    """

    @staticmethod
    def format_rate_limit_error(rate_limit_message: str | None) -> str:
        """Форматирует сообщение об ошибке rate limit.

        Args:
            rate_limit_message: Сообщение от сервиса rate limiting или None.

        Returns:
            Отформатированное сообщение об ошибке для пользователя.
        """
        return rate_limit_message or "⏰ Повторная генерация временно недоступна"

    @staticmethod
    def format_generation_limit_error(limit_message: str | None) -> str:
        """Форматирует сообщение об ошибке лимита генераций.

        Args:
            limit_message: Сообщение от сервиса проверки лимитов или None.

        Returns:
            Отформатированное сообщение об ошибке для пользователя.
        """
        if limit_message:
            return limit_message
        return "🚫 Лимит ручных генераций на этот месяц исчерпан.\nОжидайте автоматических отправок по средам."

    @staticmethod
    def get_frog_generation_status_message() -> str:
        """Возвращает текст статусного сообщения для генерации жабы.

        Returns:
            Текст статусного сообщения.
        """
        return "🐸 Генерирую жабу для вас... Это может занять несколько секунд."

    @staticmethod
    def get_frog_queue_error_message() -> str:
        """Возвращает текст сообщения об ошибке постановки в очередь.

        Returns:
            Текст сообщения об ошибке.
        """
        return "⚠️ Не удалось поставить запрос в очередь. Попробуйте позже."

    @staticmethod
    def format_command_result(result: CommandResult) -> str:
        """Форматирует результат выполнения команды.

        Args:
            result: Результат выполнения команды (CommandResult или объект с success и message).

        Returns:
            Отформатированное сообщение с результатом.
        """
        if result.success:
            return f"✅ {result.message}"
        return f"❌ {result.message}"

    @staticmethod
    def format_model_result(result: object) -> str:
        """Форматирует результат установки модели.

        Args:
            result: Результат установки модели (объект с success и message).

        Returns:
            Отформатированное сообщение с результатом.
        """
        if hasattr(result, "success") and hasattr(result, "message"):
            if result.success:
                return f"✅ {result.message}"
            return f"❌ {result.message}"
        return str(result)

    @staticmethod
    def get_model_setting_status_message() -> str:
        """Возвращает текст статусного сообщения для установки модели.

        Returns:
            Текст статусного сообщения.
        """
        return "⏳ Устанавливаю модель..."

    @staticmethod
    def format_service_error(error: Exception, max_length: int = 200) -> str:
        """Форматирует сообщение об ошибке сервиса.

        Args:
            error: Исключение, которое произошло в сервисе.
            max_length: Максимальная длина сообщения об ошибке.

        Returns:
            Отформатированное сообщение об ошибке для пользователя.
        """
        error_message = str(error)
        if len(error_message) > max_length:
            error_message = error_message[:max_length] + "..."
        return f"❌ Ошибка сервиса: {error_message}"
