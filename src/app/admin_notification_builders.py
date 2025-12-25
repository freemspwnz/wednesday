"""Билдеры для форматирования уведомлений администраторам.

Разделяют ответственность между форматированием сообщений (билдеры)
и отправкой уведомлений (AdminNotificationService).
"""

from __future__ import annotations

from dataclasses import dataclass

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
