"""Билдеры для форматирования уведомлений администраторам.

Разделяют ответственность между форматированием сообщений (билдеры)
и отправкой уведомлений (AdminNotificationService).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.admin_command_service import ChatInfo
    from app.dispatch_targets_helper import DispatchResult

# Константы для форматирования сообщений
MAX_TRACE_LENGTH = 1500
MAX_MESSAGE_LENGTH = 4000
MAX_ERROR_DETAILS_LENGTH = 500


@dataclass
class GenerationErrorData:
    """Данные для построения сообщения об ошибке генерации."""

    user_id: int
    error_details: str
    traceback_str: str | None = None


@dataclass
class DispatchErrorData:
    """Данные для построения сообщения об ошибке рассылки."""

    slot_date: str
    slot_time: str
    error_details: str
    traceback_str: str | None = None


class GenerationErrorNotificationBuilder:
    """Билдер для форматирования сообщений об ошибках генерации."""

    def __init__(self) -> None:
        """Инициализирует билдер."""
        self._max_trace_length = MAX_TRACE_LENGTH
        self._max_message_length = MAX_MESSAGE_LENGTH
        self._max_error_details_length = MAX_ERROR_DETAILS_LENGTH

    def build(self, data: GenerationErrorData) -> str:
        """Строит полное сообщение об ошибке генерации.

        Args:
            data: Данные для построения сообщения.

        Returns:
            Отформатированное сообщение.
        """
        message = (
            f"🔴 Ошибка генерации изображения по команде /frog\n\n"
            f"Пользователь: {data.user_id}\n"
            f"Детали: {data.error_details}\n"
        )

        if data.traceback_str:
            traceback = data.traceback_str
            if len(traceback) > self._max_trace_length:
                traceback = "..." + traceback[-self._max_trace_length :]
            message += f"\nТрейс (последние {self._max_trace_length} символов):\n{traceback}\n"

        message += "\nПользователю отправлено дружелюбное сообщение и случайное изображение из архива."
        return message

    def build_short(self, data: GenerationErrorData) -> str:
        """Строит короткое сообщение об ошибке генерации (без трейса).

        Args:
            data: Данные для построения сообщения.

        Returns:
            Короткое отформатированное сообщение.
        """
        error_details = data.error_details[: self._max_error_details_length]
        return (
            "🔴 Ошибка при обработке команды /frog\n\n"
            f"Пользователь: {data.user_id}\n"
            f"Детали: {error_details}\n\n"
            "⚠️ Полный трейс слишком длинный, смотрите логи.\n\n"
            "Пользователю отправлено дружелюбное сообщение и случайное изображение из архива."
        )

    def should_use_short(self, data: GenerationErrorData) -> bool:
        """Проверяет, нужно ли использовать короткое сообщение.

        Args:
            data: Данные для проверки.

        Returns:
            True если сообщение слишком длинное, False иначе.
        """
        full_message = self.build(data)
        return len(full_message) > self._max_message_length


class DispatchErrorNotificationBuilder:
    """Билдер для форматирования сообщений об ошибках рассылки."""

    def __init__(self) -> None:
        """Инициализирует билдер."""
        self._max_trace_length = MAX_TRACE_LENGTH
        self._max_message_length = MAX_MESSAGE_LENGTH
        self._max_error_details_length = MAX_ERROR_DETAILS_LENGTH

    def build(self, data: DispatchErrorData) -> str:
        """Строит полное сообщение об ошибке рассылки.

        Args:
            data: Данные для построения сообщения.

        Returns:
            Отформатированное сообщение.
        """
        message = (
            f"🔴 Ошибка рассылки Wednesday Frog\n\n"
            f"Слот: {data.slot_date} {data.slot_time}\n"
            f"Детали: {data.error_details}\n"
        )

        if data.traceback_str:
            traceback = data.traceback_str
            if len(traceback) > self._max_trace_length:
                traceback = "..." + traceback[-self._max_trace_length :]
            message += f"\nТрейс (последние {self._max_trace_length} символов):\n{traceback}\n"

        message += "\nПользователям отправлено fallback изображение из архива."
        return message

    def build_short(self, data: DispatchErrorData) -> str:
        """Строит короткое сообщение об ошибке рассылки (без трейса).

        Args:
            data: Данные для построения сообщения.

        Returns:
            Короткое отформатированное сообщение.
        """
        error_details = data.error_details[: self._max_error_details_length]
        return (
            f"🔴 Ошибка рассылки Wednesday Frog\n\n"
            f"Слот: {data.slot_date} {data.slot_time}\n"
            f"Детали: {error_details}\n\n"
            "⚠️ Полный трейс слишком длинный, смотрите логи.\n\n"
            "Пользователям отправлено fallback изображение из архива."
        )

    def should_use_short(self, data: DispatchErrorData) -> bool:
        """Проверяет, нужно ли использовать короткое сообщение.

        Args:
            data: Данные для проверки.

        Returns:
            True если сообщение слишком длинное, False иначе.
        """
        full_message = self.build(data)
        return len(full_message) > self._max_message_length


@dataclass
class AdminInfo:
    """Информация об администраторе для форматирования."""

    admin_id: int
    name: str
    username: str | None = None
    is_super_admin: bool = False


class AdminNotificationBuilders:
    """Билдеры для форматирования административных сообщений.

    Инкапсулирует логику форматирования сообщений для админских команд,
    обеспечивая единообразное представление информации.
    """

    @staticmethod
    def build_chat_list_message(chat_infos: list[ChatInfo]) -> str:
        """Форматирует список чатов для отображения.

        Args:
            chat_infos: Список информации о чатах.

        Returns:
            Отформатированное сообщение со списком чатов.
        """
        if not chat_infos:
            return "📭 Нет активных чатов"

        chat_list = []
        for info in chat_infos:
            title = info.title or "Unknown"
            chat_list.append(f"• {title} (ID: {info.chat_id})")

        return (
            "📋 Активные чаты для отправки:\n\n"
            + "\n".join(chat_list)
            + "\n\n"
            + "💡 Использование:\n"
            + "• /force_send <chat_id> — отправить жабу в указанный чат\n"
            + "• /force_send all — отправить жабу во все чаты"
        )

    @staticmethod
    def build_admin_list_message(admins: list[AdminInfo]) -> str:
        """Форматирует список администраторов с полной информацией.

        Args:
            admins: Список информации об администраторах.

        Returns:
            Отформатированное сообщение со списком администраторов.
        """
        if not admins:
            return "📭 Нет администраторов"

        admin_list = []
        for admin in admins:
            username_text = f" (@{admin.username})" if admin.username else ""
            super_text = " (главный)" if admin.is_super_admin else ""
            admin_list.append(f"• ID: {admin.admin_id} ({admin.name}{username_text}){super_text}")

        return "👥 Список администраторов:\n\n" + "\n".join(admin_list)

    @staticmethod
    def build_simple_admin_list_message(
        admins: list[int],
        super_admin_id: int | None,
    ) -> str:
        """Форматирует простой список администраторов только с ID.

        Args:
            admins: Список ID администраторов.
            super_admin_id: ID главного администратора (опционально).

        Returns:
            Отформатированное сообщение со списком администраторов.
        """
        if not admins:
            return "📭 Нет администраторов"

        admin_list = []
        for admin_id in admins:
            is_main = " (главный)" if (super_admin_id and super_admin_id == admin_id) else ""
            admin_list.append(f"• ID: {admin_id}{is_main}")

        return "👥 Список администраторов:\n\n" + "\n".join(admin_list)

    @staticmethod
    def build_force_send_result_message(
        delivery_result: DispatchResult,
        used_fallback: bool,
    ) -> str:
        """Форматирует результат выполнения команды /force_send.

        Args:
            delivery_result: Результат отправки изображений.
            used_fallback: Флаг использования fallback изображения.

        Returns:
            Отформатированное сообщение с результатом отправки.
        """
        return (
            f"✅ Отправка выполнена:\n"
            f"• Успешно: {delivery_result.success_count}/{delivery_result.total_targets}\n"
            f"• Ошибок: {delivery_result.failed_count}\n"
            f"• Использован: {'fallback (лимит исчерпан)' if used_fallback else 'новая генерация'}"
        )

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
