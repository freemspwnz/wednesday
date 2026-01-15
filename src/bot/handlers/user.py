from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.frog_limit_service import FrogRateLimiterService
from bot.handlers.base import BaseHandlers
from bot.handlers.messages import WELCOME_MESSAGE_START
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger


class UserHandlers(BaseHandlers):
    """Обработчики пользовательских команд бота.

    Этот класс инкапсулирует только пользовательские команды (/start, /help, /frog)
    и обработчик неизвестных команд. Содержит полную реализацию всех методов.
    """

    def __init__(
        self,
        services: BotServices,
        logger: ILogger,
    ) -> None:
        super().__init__(services, logger)
        if self.services.admin_access_service is None:
            raise ValueError("admin_access_service must be provided in BotServices")
        if self.services.help_message_service is None:
            raise ValueError("help_message_service must be provided in BotServices")
        self._admin_access = self.services.admin_access_service
        self._help_message_service = self.services.help_message_service

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start.

        Приветствует пользователя и показывает основную информацию о боте,
        включая доступные команды.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Отправляет приветственное сообщение пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        self.logger.info(f"Получена команда /start от пользователя {update.effective_user.id}")

        welcome_message = WELCOME_MESSAGE_START

        success = await self._safe_reply_with_fallback(
            update.message,
            welcome_message,
        )
        if success:
            self.logger.info("Отправлено приветственное сообщение")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help.

        Показывает справку по командам бота. Для администраторов отображается
        расширенная админская справка со всеми доступными командами, для обычных
        пользователей - пользовательская справка с базовыми командами.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Проверяет права администратора через admins_store.is_admin().
            - Отправляет соответствующую справку (админскую или пользовательскую).
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /help от пользователя {user_id}")

        # Проверка доступа администратора через admin_access_service
        is_admin = await self._admin_access.is_admin(user_id)

        # Получаем сообщение справки через сервис
        if is_admin:
            help_message = self._help_message_service.build_admin_help_message()
            self.logger.info("Отправлена админская справка")
        else:
            help_message = self._help_message_service.build_user_help_message()
            self.logger.info("Отправлена пользовательская справка")

        await self._safe_reply_with_fallback(
            update.message,
            help_message,
        )

    async def frog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /frog.

        Ставит задачу генерации и отправки изображения жабы в очередь Celery.
        Команда защищена rate limiting (per-user и глобальный) и проверкой
        месячного лимита генераций.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к объекту бота и Celery‑контексту.
                Информация о лимитах и использовании берётся из self.services.usage.

        Side Effects:
            - Проверяет глобальный и per-user rate limits через FrogRateLimiterService.
            - Проверяет месячный лимит генераций через usage.can_use_frog().
            - Отправляет статусное сообщение пользователю.
            - Ставит Celery-задачу через ITaskQueue.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        chat_id = update.message.chat_id
        self.logger.info(f"Получена команда /frog от пользователя {user_id}")

        # Проверка на админа через admin_access_service
        is_admin = await self._admin_access.is_admin(user_id)

        # Проверка rate limit через application service
        is_allowed, rate_limit_message = await self.services.frog_rate_limiter.check_and_consume(
            user_id=user_id,
            is_admin=is_admin,
        )
        if not is_allowed:
            error_message = rate_limit_message or "⏰ Повторная генерация временно недоступна"
            await self._safe_reply_with_fallback(update.message, error_message)
            return

        # Проверяем лимит генераций через frog_rate_limiter
        can_generate, limit_message = await self.services.frog_rate_limiter.check_generation_allowed()
        if not can_generate:
            error_message = FrogRateLimiterService.format_generation_limit_error(limit_message)
            await self._safe_reply_with_fallback(update.message, error_message)
            return

        # Отправляем сообщение о начале генерации
        status_message = await self._safe_reply_text_and_get_message(
            update.message,
            "🐸 Генерирую жабу для вас... Это может занять несколько секунд.",
        )

        # Ставим задачу в очередь Celery напрямую
        try:
            await self.services.task_queue.send_frog_manual_task(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message.message_id if status_message else None,
            )
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу в очередь Celery: {e}")
            # Удаляем статусное сообщение
            await self._safe_delete_message(status_message)
            # Отправляем сообщение пользователю об ошибке
            await self._safe_reply_with_fallback(
                update.message,
                "⚠️ Не удалось поставить запрос в очередь. Попробуйте позже.",
            )

    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик неизвестных команд.

        Обрабатывает любые команды, которые не распознаны другими обработчиками.
        Отправляет пользователю сообщение с подсказкой о доступных командах.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Отправляет сообщение с информацией о доступных командах пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена неизвестная команда от пользователя {user_id}")

        unknown_message = (
            "❓ Неизвестная команда!\n\n"
            "Доступные команды:\n"
            "/start - Приветствие\n"
            "/help - Справка\n"
            "/frog - Сгенерировать жабу\n\n"
            "Используйте /help для получения подробной информации."
        )

        success = await self._safe_reply_with_fallback(
            update.message,
            unknown_message,
        )
        if success:
            self.logger.info("Отправлено сообщение о неизвестной команде")
