"""Координатор состояния между основным и резервным ботом."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from shared.protocols import ILogger

if TYPE_CHECKING:
    from telegram import Bot


@dataclass
class BotStateData:
    """Данные для координации состояния между ботами."""

    chat_id: str | int | None
    message_id: int | None


class BotStateCoordinator:
    """Координирует состояние между основным и резервным ботом.

    Обрабатывает редактирование статусных сообщений при запуске и остановке бота.
    Используется для синхронизации состояния между WednesdayBot и SupportBot.
    """

    def __init__(self, logger: ILogger, admin_chat_id: int | None = None) -> None:
        """Инициализирует координатор состояния.

        Args:
            logger: Экземпляр логгера.
            admin_chat_id: ID админ-чата для исключения из редактирования (опционально).
        """
        self._logger = logger
        self._admin_chat_id = admin_chat_id

    @staticmethod
    def is_admin_chat(chat_id: str | int | None, admin_chat_id: int | None) -> bool:
        """Проверяет, является ли чат админским.

        Безопасно сравнивает chat_id с admin_chat_id, обрабатывая
        различные типы (str, int, None) и ошибки преобразования.

        Args:
            chat_id: ID чата для проверки (может быть str, int или None).
            admin_chat_id: ID админ-чата из настроек (int | None).

        Returns:
            True если chat_id совпадает с admin_chat_id, False иначе.
        """
        if admin_chat_id is None or chat_id is None:
            return False

        try:
            chat_id_int = int(str(chat_id))
            return chat_id_int == admin_chat_id
        except (ValueError, TypeError, AttributeError):
            return False

    async def handle_startup_edit(
        self,
        bot: Bot,
        state_data: BotStateData | None,
    ) -> None:
        """Обрабатывает редактирование статусного сообщения при запуске.

        Редактирует сообщение от SupportBot, уведомляя о том, что основной бот запущен.
        Не редактирует сообщение в админском чате.

        Args:
            bot: Экземпляр Telegram Bot для редактирования сообщения.
            state_data: Данные для редактирования сообщения (chat_id, message_id).
        """
        if not state_data or not state_data.chat_id or not state_data.message_id:
            return

        try:
            # Не редактируем сообщение в админском чате
            if self.is_admin_chat(state_data.chat_id, self._admin_chat_id):
                self._logger.info("Пропускаю редактирование статусного сообщения в админском чате")
                return

            # Редактируем сообщение с финальным состоянием
            final_text = "🛑 Support Bot остановлен\n✅ Wednesday Frog Bot запущен"
            await bot.edit_message_text(
                chat_id=state_data.chat_id,
                message_id=state_data.message_id,
                text=final_text,
            )
            self._logger.info("Основной бот подтвердил запуск в сообщение SupportBot")
        except Exception as e:
            self._logger.warning(f"Не удалось обновить статусное сообщение SupportBot: {e}")

    async def handle_shutdown_edit(
        self,
        bot: Bot,
        state_data: BotStateData | None,
    ) -> None:
        """Обрабатывает редактирование статусного сообщения при остановке.

        Редактирует сообщение, уведомляя о том, что основной бот остановлен.
        Не редактирует сообщение в админском чате.

        Args:
            bot: Экземпляр Telegram Bot для редактирования сообщения.
            state_data: Данные для редактирования сообщения (chat_id, message_id).
        """
        if not state_data or not state_data.chat_id or not state_data.message_id:
            return

        try:
            # Не редактируем сообщение в админском чате
            if self.is_admin_chat(state_data.chat_id, self._admin_chat_id):
                self._logger.info(
                    "Пропускаю редактирование статусного сообщения в админском чате (остановка основного)",
                )
                return

            # Редактируем сообщение с финальным состоянием
            await bot.edit_message_text(
                chat_id=state_data.chat_id,
                message_id=state_data.message_id,
                text="🛑 Wednesday Frog Bot остановлен!",
            )
            self._logger.info("Статусное сообщение обновлено: основной бот остановлен")
        except Exception as e:
            self._logger.warning(f"Не удалось обновить статусное сообщение об остановке: {e}")

    async def handle_support_startup_edit(
        self,
        bot: Bot,
        state_data: BotStateData | None,
    ) -> None:
        """Обрабатывает редактирование статусного сообщения при запуске SupportBot.

        Редактирует сообщение от основного бота, уведомляя о том, что SupportBot запущен.
        Используется в SupportBot.start() для обновления сообщения об остановке основного бота.
        Не редактирует сообщение в админском чате.

        Args:
            bot: Экземпляр Telegram Bot для редактирования сообщения.
            state_data: Данные для редактирования сообщения (chat_id, message_id).
        """
        if not state_data or not state_data.chat_id or not state_data.message_id:
            return

        try:
            # Не редактируем сообщение в админском чате
            if self.is_admin_chat(state_data.chat_id, self._admin_chat_id):
                self._logger.info("SupportBot: пропускаю редактирование статусного сообщения в админском чате")
                return

            # Редактируем сообщение с финальным состоянием для SupportBot
            final_text = "🛑  Wednesday Frog Bot остановлен\n✅ Резервный бот запущен"
            await bot.edit_message_text(
                chat_id=state_data.chat_id,
                message_id=state_data.message_id,
                text=final_text,
            )
            self._logger.info("Сообщение об остановке обновлено в чате-источнике")
        except Exception as e:
            # Игнорируем ошибку "Message is not modified" — это нормально, если текст уже установлен
            error_str = str(e).lower()
            if "message is not modified" in error_str or "not modified" in error_str:
                self._logger.debug("Сообщение уже имеет нужный текст, пропускаем редактирование")
            else:
                self._logger.warning(f"Не удалось обновить сообщение об остановке: {e}")

    async def handle_support_shutdown_edit(
        self,
        bot: Bot,
        state_data: BotStateData | None,
    ) -> None:
        """Обрабатывает редактирование статусного сообщения при остановке SupportBot.

        Редактирует сообщение, уведомляя о том, что SupportBot остановлен и основной бот запускается.
        Используется в SupportBot.stop() для обновления сообщения о запуске основного бота.
        Не редактирует сообщение в админском чате.

        Args:
            bot: Экземпляр Telegram Bot для редактирования сообщения.
            state_data: Данные для редактирования сообщения (chat_id, message_id).
        """
        if not state_data or not state_data.chat_id or not state_data.message_id:
            return

        try:
            # Не редактируем сообщение в админском чате
            if self.is_admin_chat(state_data.chat_id, self._admin_chat_id):
                return  # Пропускаем для админского чата

            # Редактируем сообщение с промежуточным состоянием
            interim_text = "🚀 Запускаю основной бот...\n🛑 Support Bot остановлен"
            await bot.edit_message_text(
                chat_id=state_data.chat_id,
                message_id=state_data.message_id,
                text=interim_text,
            )
        except Exception as e:
            # Игнорируем ошибки при редактировании, так как это не критично
            self._logger.debug(f"Не удалось обновить сообщение при остановке SupportBot: {e}")
