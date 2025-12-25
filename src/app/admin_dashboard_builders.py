"""Билдеры для форматирования сообщений админского дашборда.

Разделяют ответственность между сбором данных (AdminDashboardService)
и форматированием сообщений (билдеры).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

# Магические числа, связанные с форматированием и усечением сообщений
TELEGRAM_SAFE_MESSAGE_LENGTH = 4000


class MetricsSummary(TypedDict, total=False):
    """Типизированная структура сводки метрик производительности.

    Используется для типизации возвращаемого значения IMetrics.get_summary().
    Все поля опциональны, так как метрики могут быть не настроены.
    """

    generations_total: int
    generations_success: int
    generations_failed: int
    generations_retries: int
    average_generation_time: str
    dispatches_success: int
    dispatches_failed: int
    circuit_breaker_trips: int


@dataclass
class StatusData:
    """Данные для построения сообщения статуса бота."""

    bot_name: str
    next_run_line: str
    api_status: str

    # Сырые данные вместо отформатированных строк
    kandinsky_current_id: str | None
    kandinsky_current_name: str | None

    gigachat_status: str
    gigachat_current: str | None

    scheduler_status: str

    # Сырые данные для usage_info
    usage_total: int | None
    usage_threshold: int | None
    usage_quota: int | None

    # Сырые данные для chats_info
    chats_count: int | None

    # Сырые данные для metrics_text
    metrics_summary: MetricsSummary | None


class StatusMessageBuilder:
    """Билдер для форматирования сообщения статуса бота."""

    PERCENT_MULTIPLIER = 100  # Константа для вычисления процентов

    def __init__(self) -> None:
        """Инициализирует билдер."""
        self._telegram_safe_length = TELEGRAM_SAFE_MESSAGE_LENGTH

    def _format_usage_info(
        self,
        total: int | None,
        threshold: int | None,
        quota: int | None,
    ) -> str:
        """Форматирует информацию об использовании.

        Args:
            total: Количество использований.
            threshold: Порог.
            quota: Квота.

        Returns:
            Отформатированная строка информации об использовании.
        """
        if total is None or threshold is None or quota is None:
            return "N/A"

        used_percent = int(total / quota * self.PERCENT_MULTIPLIER) if quota else 0
        return f"{total}/{quota} ({used_percent}%), порог: {threshold}"

    @staticmethod
    def _format_chats_info(chats_count: int | None) -> str:
        """Форматирует информацию о чатах.

        Args:
            chats_count: Количество активных чатов.

        Returns:
            Отформатированная строка с количеством чатов.
        """
        if chats_count is None:
            return "N/A"
        return str(chats_count)

    def _format_metrics_text(self, metrics_summary: MetricsSummary | None) -> str:
        """Форматирует метрики производительности.

        Args:
            metrics_summary: Словарь с метриками.

        Returns:
            Отформатированный текст метрик.
        """
        if not metrics_summary:
            return "Не настроены"

        total_requests = metrics_summary.get("generations_total", 0)
        successful = metrics_summary.get("generations_success", 0)
        success_rate = (successful / total_requests * self.PERCENT_MULTIPLIER) if total_requests > 0 else 0

        return (
            f"• Всего запросов на генерацию: {total_requests}\n"
            f"• Успешных генераций: {successful}\n"
            f"• Процент успеха: {success_rate:.1f}%\n"
            f"• Среднее время генерации: {metrics_summary.get('average_generation_time', 'N/A')}\n"
            f"• Срабатываний circuit breaker: {metrics_summary.get('circuit_breaker_trips', 0)}"
        )

    @staticmethod
    def _format_kandinsky_current(
        current_id: str | None,
        current_name: str | None,
    ) -> str:
        """Форматирует информацию о текущей модели Kandinsky.

        Args:
            current_id: ID текущей модели.
            current_name: Название текущей модели.

        Returns:
            Отформатированная строка с информацией о модели.
        """
        if current_id:
            model_display = current_name or current_id
            return f"  ⭐ Текущая модель: {model_display}"
        return "  ⚠️ Модель не выбрана"

    @staticmethod
    def _format_gigachat_current(current: str | None) -> str:
        """Форматирует информацию о текущей модели GigaChat.

        Args:
            current: Текущая модель GigaChat.

        Returns:
            Отформатированная строка с информацией о модели.
        """
        if current:
            return f"  ⭐ Текущая модель: {current}"
        return "  ⚠️ Модель не выбрана"

    def build(self, data: StatusData) -> str:
        """Строит текст сообщения статуса на основе данных.

        Args:
            data: Данные для построения сообщения.

        Returns:
            Отформатированное сообщение статуса, обрезанное до безопасной длины Telegram.
        """
        # Форматируем данные через методы билдера
        usage_info = self._format_usage_info(
            data.usage_total,
            data.usage_threshold,
            data.usage_quota,
        )
        chats_info = StatusMessageBuilder._format_chats_info(data.chats_count)
        metrics_text = self._format_metrics_text(data.metrics_summary)
        kandinsky_current_text = StatusMessageBuilder._format_kandinsky_current(
            data.kandinsky_current_id,
            data.kandinsky_current_name,
        )
        gigachat_current_text = StatusMessageBuilder._format_gigachat_current(data.gigachat_current)

        message = (
            f"🤖 Статус бота: {data.bot_name}\n\n"
            "✅ Бот активен и работает\n"
            f"{data.next_run_line}"
            "🎨 Генератор изображений: Kandinsky API\n"
            "📝 Логирование: включено\n\n"
            "🔌 Проверка систем:\n"
            f"• API Kandinsky: {data.api_status}\n"
            f"{kandinsky_current_text}\n"
            f"• API GigaChat: {data.gigachat_status}\n"
            f"{gigachat_current_text}\n"
            f"• Планировщик: {data.scheduler_status}\n\n"
            "📊 Статистика:\n"
            f"• Генерации: {usage_info}\n"
            f"• Активных чатов: {chats_info}\n\n"
            "📈 Метрики производительности:\n"
            f"{metrics_text}\n\n"
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
