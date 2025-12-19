"""Билдеры для форматирования сообщений админского дашборда.

Разделяют ответственность между сбором данных (AdminDashboardService)
и форматированием сообщений (билдеры).
"""

from __future__ import annotations

from dataclasses import dataclass

# Магические числа, связанные с форматированием и усечением сообщений
TELEGRAM_SAFE_MESSAGE_LENGTH = 4000


@dataclass
class StatusData:
    """Данные для построения сообщения статуса бота."""

    bot_name: str
    next_run_line: str
    api_status: str
    kandinsky_current_text: str
    gigachat_status: str
    gigachat_current_text: str
    scheduler_status: str
    usage_info: str
    chats_info: str | int
    metrics_text: str


class StatusMessageBuilder:
    """Билдер для форматирования сообщения статуса бота."""

    def __init__(self) -> None:
        """Инициализирует билдер."""
        self._telegram_safe_length = TELEGRAM_SAFE_MESSAGE_LENGTH

    def build(self, data: StatusData) -> str:
        """Строит текст сообщения статуса на основе данных.

        Args:
            data: Данные для построения сообщения.

        Returns:
            Отформатированное сообщение статуса, обрезанное до безопасной длины Telegram.
        """
        message = (
            f"🤖 Статус бота: {data.bot_name}\n\n"
            "✅ Бот активен и работает\n"
            f"{data.next_run_line}"
            "🎨 Генератор изображений: Kandinsky API\n"
            "📝 Логирование: включено\n\n"
            "🔌 Проверка систем:\n"
            f"• API Kandinsky: {data.api_status}\n"
            f"{data.kandinsky_current_text}\n"
            f"• API GigaChat: {data.gigachat_status}\n"
            f"{data.gigachat_current_text}\n"
            f"• Планировщик: {data.scheduler_status}\n\n"
            "📊 Статистика:\n"
            f"• Генерации: {data.usage_info}\n"
            f"• Активных чатов: {data.chats_info}\n\n"
            "📈 Метрики производительности:\n"
            f"{data.metrics_text}\n\n"
            "💡 Используйте /list_models для просмотра всех доступных моделей\n\n"
            "🔄 Последняя проверка: прямо сейчас\n"
            "💚 Все системы работают нормально!"
        )
        return message[: self._telegram_safe_length]


@dataclass
class ModelsListData:
    """Данные для построения сообщения списка моделей."""

    kandinsky_models: list[str]
    kandinsky_current: tuple[str | None, str | None]
    gigachat_models: list[str]
    gigachat_current: str | None
    gigachat_configured: bool


class ModelsListMessageBuilder:
    """Билдер для форматирования сообщения списка моделей."""

    def __init__(self) -> None:
        """Инициализирует билдер."""
        self._telegram_safe_length = TELEGRAM_SAFE_MESSAGE_LENGTH

    def build(self, data: ModelsListData) -> str:
        """Строит текст сообщения списка моделей на основе данных.

        Args:
            data: Данные для построения сообщения.

        Returns:
            Отформатированное сообщение списка моделей, обрезанное до безопасной длины Telegram.
        """
        message_parts: list[str] = ["📋 Доступные модели:\n"]

        # Kandinsky
        if data.kandinsky_models:
            message_parts.append("🎨 Kandinsky (Kandinsky API):")
            for model in data.kandinsky_models:
                is_current = ""
                if data.kandinsky_current[0]:
                    model_str = str(model)
                    if data.kandinsky_current[0] in model_str:
                        is_current = " ⭐"
                message_parts.append(f"  • {model}{is_current}")
        else:
            message_parts.append("🎨 Kandinsky: не удалось получить список моделей")
            if data.kandinsky_current[0]:
                message_parts.append(
                    f"  Текущая: {data.kandinsky_current[1] or data.kandinsky_current[0]}",
                )

        message_parts.append("")  # пустая строка между секциями

        # GigaChat
        if data.gigachat_configured:
            if data.gigachat_models:
                message_parts.append("🤖 GigaChat (GigaChat API):")
                for model in data.gigachat_models:
                    is_current = " ⭐" if (data.gigachat_current and model == data.gigachat_current) else ""
                    message_parts.append(f"  • {model}{is_current}")
            else:
                message_parts.append("🤖 GigaChat: не удалось получить список моделей")
                if data.gigachat_current:
                    message_parts.append(f"  Текущая: {data.gigachat_current}")
        else:
            message_parts.append("🤖 GigaChat: не настроен (GIGACHAT_AUTHORIZATION_KEY не указан)")

        message = "\n".join(message_parts)

        if len(message) > self._telegram_safe_length:
            truncated_parts = message_parts[: len(message_parts) // 2]
            message = "\n".join(truncated_parts) + "\n\n⚠️ Сообщение обрезано, часть моделей не показана"

        return message
