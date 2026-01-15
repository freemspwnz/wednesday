from __future__ import annotations

from telegram import Bot, Chat, Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from bot.handlers.base import (
    BaseHandlers,
)
from shared.base.exceptions import (
    AccessDeniedError,
    RepoError,
    ServiceError,
)
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger
from shared.retry import retry_on_connect_error

# Константы
MAX_FROG_THRESHOLD = 100  # максимальный порог ручных генераций
MAX_ERROR_DETAILS_LENGTH = 500  # максимальная длина деталей ошибки
PERCENT_MULTIPLIER = 100  # множитель для процентов
TELEGRAM_SAFE_MESSAGE_LENGTH = 4000  # безопасная длина для обрезки сообщений


class AdminHandlers(BaseHandlers):
    """Обработчики административных команд бота.

    Инкапсулирует команды управления ботом, логами, чатами и администраторами.
    Содержит полную реализацию всех административных команд.
    """

    def __init__(
        self,
        services: BotServices,
        logger: ILogger,
    ) -> None:
        super().__init__(services, logger)
        if self.services.admin_dashboard_service is None:
            raise ValueError("admin_dashboard_service must be provided in BotServices")
        if self.services.admin_access_service is None:
            raise ValueError("admin_access_service must be provided in BotServices")
        if self.services.admin_command_service is None:
            raise ValueError("admin_command_service must be provided in BotServices")
        if self.services.chat_info_service is None:
            raise ValueError("chat_info_service must be provided in BotServices")
        self._dashboard_service = self.services.admin_dashboard_service
        self._admin_access = self.services.admin_access_service
        self._admin_command = self.services.admin_command_service
        self._chat_info_service = self.services.chat_info_service

    async def _get_chat_info_safe(
        self,
        bot: Bot,
        chat_id: int,
        timeout: float = 5.0,
    ) -> tuple[str | int, str]:
        """Безопасно получает информацию о чате с обработкой ошибок и rate limiting.

        Делегирует выполнение в ChatInfoService для соблюдения архитектурных границ.
        Использует rate limiting для защиты от превышения лимитов Telegram API.

        Args:
            bot: Экземпляр Telegram бота (не используется, оставлен для обратной совместимости).
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах.

        Returns:
            Кортеж (chat_id, title), где chat_id может быть str или int,
            title - название чата или сообщение об ошибке.
        """
        # Получаем rate limiter через services (если доступен)
        rate_limiter = getattr(self.services, "telegram_api_rate_limiter", None)

        if rate_limiter:
            # Используем проактивную защиту через rate limiter
            async def _get_info() -> tuple[str | int, str]:
                result = await self._chat_info_service.get_chat_info_safe(chat_id, timeout)
                return result

            result: tuple[str | int, str] = await rate_limiter.execute_with_rate_limit(_get_info)
            return result
        else:
            # Fallback без rate limiting (для обратной совместимости)
            return await self._chat_info_service.get_chat_info_safe(chat_id, timeout)

    async def _get_chat_safe(
        self,
        bot: Bot,
        chat_id: int,
        timeout: float = 10.0,
    ) -> Chat | None:
        """Безопасно получает полный объект чата с обработкой ошибок и rate limiting.

        Делегирует выполнение в ChatInfoService для соблюдения архитектурных границ.
        Использует rate limiting для защиты от превышения лимитов Telegram API.

        Args:
            bot: Экземпляр Telegram бота (не используется, оставлен для обратной совместимости).
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах (по умолчанию 10 секунд).

        Returns:
            Объект чата или None в случае ошибки.
        """
        # Получаем rate limiter через services (если доступен)
        rate_limiter = getattr(self.services, "telegram_api_rate_limiter", None)

        if rate_limiter:
            # Используем проактивную защиту через rate limiter
            async def _get_chat() -> Chat | None:
                result = await self._chat_info_service.get_chat_safe(chat_id, timeout)
                return result

            result: Chat | None = await rate_limiter.execute_with_rate_limit(_get_chat)
            return result
        else:
            # Fallback без rate limiting (для обратной совместимости)
            return await self._chat_info_service.get_chat_safe(chat_id, timeout)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /status.

        Показывает расширенный статус бота, включая информацию о статусе бота,
        планировщике, лимитах генераций, активных чатах, проверку API (Kandinsky и GigaChat)
        и метрики производительности. Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к Telegram‑боту через context.bot
                для получения информации о боте. Хранилища (usage, chats, metrics)
                берутся из self.services.*.

        Side Effects:
            - Вызывает admin_dashboard_service.build_status_message() для получения статуса.
            - Получает информацию о лимитах через usage.get_limits_info().
            - Получает список чатов через chats.list_chat_ids().
            - Получает метрики через metrics.get_summary().
            - Отправляет подробный статус пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /status от пользователя {user_id}")

        # Проверка доступа администратора
        if not await self._admin_access.is_admin(user_id):
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только администратору",
            )
            return

        async def _execute_status() -> None:
            bot_info = await context.bot.get_me()
            status_message = await self._dashboard_service.build_status_message(
                bot_name=bot_info.first_name,
            )

            # update.message гарантированно не None после проверки выше
            message = update.message
            assert message is not None  # для mypy
            success = await self._safe_reply_with_fallback(
                message,
                status_message,
                fallback_text="❌ Ошибка при получении статуса",
            )
            if success:
                self.logger.info("Отправлен статус бота")

        await self._handle_command_errors(update, _execute_status)

    async def admin_force_send_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /force_send.

        Выполняет принудительную отправку изображения жабы в указанный чат(ы)
        или во все активные чаты. Команда доступна только администраторам.
        Без аргументов показывает список активных чатов.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к самому Telegram‑боту через context.bot.
                Список целевых чатов и лимиты использования берутся из self.services.chats
                и self.services.usage.

        Side Effects:
            - Вызывает image_generator.generate_frog_image() для генерации нового изображения
              (если лимит не исчерпан).
            - Использует image_generator.get_random_saved_image() как fallback при недоступности генерации.
            - Отправляет изображение в указанные чаты через context.bot.send_image().
            - Вызывает usage.increment() для увеличения счетчика использования.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /force_send от пользователя {user_id}")

        if not await self.admins_store.is_admin(user_id):
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только администратору",
            )
            return

        # Без аргументов - показываем список чатов
        if not context.args or len(context.args) == 0:
            result = await self._admin_command.get_chat_list_for_display()
            await self._safe_reply_with_fallback(
                update.message,
                result.message,
            )
            return

        # Делегируем всю бизнес-логику в сервис
        arg = context.args[0].strip().lower()
        try:
            result = await self._admin_command.execute_force_send(
                requester_user_id=user_id,
                target_arg=arg,
            )
            await self._safe_reply_with_fallback(
                update.message,
                result.message,
            )
            if result.success:
                self.logger.info(f"Команда /force_send выполнена пользователем {user_id}")
        except ServiceError as e:
            self.logger.error(
                f"Ошибка сервиса при выполнении force_send: {e}",
                event="force_send_service_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            await self._safe_reply_with_fallback(
                update.message,
                f"❌ Ошибка сервиса: {str(e)[:200]}",
            )

    async def admin_add_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /add_chat.

        Добавляет чат в список рассылки для автоматических отправок.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args. Хранилище чатов берётся из self.services.chats.

        Side Effects:
            - Вызывает chats.add_chat() для добавления чата в хранилище.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.

        Raises:
            ValueError: Если переданный chat_id не является числом.
        """
        if not update.message or not update.effective_user:
            return

        if not await self.admins_store.is_admin(update.effective_user.id):
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только администратору",
            )
            return

        if not context.args or len(context.args) == 0:
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: /add_chat <chat_id>",
            )
            return

        try:
            chat_id = int(context.args[0])
            # Валидация через сервис
            from app.admin_command_service import AdminCommandService

            validation_result = AdminCommandService.validate_chat_id(chat_id)
            if not validation_result.is_valid:
                await self._safe_reply_with_fallback(
                    update.message,
                    f"❌ {validation_result.error_message or 'Неверный chat_id'}",
                )
                return

            result = await self._admin_command.add_chat(chat_id, "Manually added")
            if result.success:
                self.logger.info(f"Чат {chat_id} успешно добавлен в рассылку")
            else:
                self.logger.warning(f"Не удалось добавить чат {chat_id}: {result.message}")
            await self._safe_reply_with_fallback(
                update.message,
                result.message,
            )
        except ValueError as e:
            error_msg = str(e) if str(e) else "Неверный chat_id (должен быть числом в допустимом диапазоне)"
            await self._safe_reply_with_fallback(
                update.message,
                f"❌ {error_msg}",
            )

    async def admin_remove_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /remove_chat.

        Удаляет чат из списка рассылки для автоматических отправок.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args. Хранилище чатов берётся из self.services.chats.

        Side Effects:
            - Вызывает chats.remove_chat() для удаления чата из хранилища.
            - Отправляет ответное сообщение пользователю с результатом операции.

        Raises:
            ValueError: Если переданный chat_id не является числом.
        """
        if not update.message or not update.effective_user:
            return

        if not await self.admins_store.is_admin(update.effective_user.id):
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только администратору",
            )
            return

        if not context.args or len(context.args) == 0:
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: /remove_chat <chat_id>",
            )
            return

        try:
            chat_id = int(context.args[0])
            # Валидация через сервис
            from app.admin_command_service import AdminCommandService

            validation_result = AdminCommandService.validate_chat_id(chat_id)
            if not validation_result.is_valid:
                await self._safe_reply_with_fallback(
                    update.message,
                    f"❌ {validation_result.error_message or 'Неверный chat_id'}",
                )
                return

            result = await self._admin_command.remove_chat(chat_id)
            if result.success:
                self.logger.info(f"Чат {chat_id} успешно удалён из рассылки")
            else:
                self.logger.warning(f"Не удалось удалить чат {chat_id}: {result.message}")
            await self._safe_reply_with_fallback(
                update.message,
                result.message,
            )
        except ValueError as e:
            error_msg = str(e) if str(e) else "Неверный chat_id (должен быть числом в допустимом диапазоне)"
            await self._safe_reply_with_fallback(
                update.message,
                f"❌ {error_msg}",
            )

    async def list_chats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /list_chats.

        Возвращает список всех активных чатов с их ID и названиями.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к Telegram‑боту
                для получения информации о чатах через context.bot.get_chat().
                Список ID чатов берётся из self.services.chats.

        Side Effects:
            - Вызывает chats.list_chat_ids() для получения списка ID чатов.
            - Вызывает context.bot.get_chat() для каждого чата для получения названия.
            - Отправляет форматированный список чатов пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /list_chats от пользователя {user_id}")

        if not await self.admins_store.is_admin(user_id):
            if not await self._safe_reply_text_with_error_logging(
                update.message,
                "❌ Доступно только администратору",
                error_context="сообщение об ограничении доступа",
                max_retries=3,
                delay=2,
            ):
                return
            return

        # Делегируем получение и форматирование списка чатов в сервис
        result = await self._admin_command.get_chat_list_for_display()
        await self._safe_reply_with_fallback(
            update.message,
            result.message,
        )
        if result.success:
            self.logger.info(f"Отправлен список чатов пользователю {user_id}")

    async def set_frog_limit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_frog_limit.

        Устанавливает порог ручных генераций /frog (максимум 100).
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, используемый для доступа к аргументам команды
                через context.args. Данные об использовании берутся из self.services.usage.

        Side Effects:
            - Вызывает usage.set_frog_threshold() для установки нового порога.
            - Отправляет ответное сообщение пользователю с результатом операции.

        Raises:
            ValueError: Если переданный аргумент не является положительным числом.
        """
        self.logger.info("Начало выполнения команды set_frog_limit_command")
        if not update.message or not update.effective_user:
            self.logger.warning("set_frog_limit_command: update.message или update.effective_user отсутствует")
            return

        user_id = update.effective_user.id
        self.logger.info(f"set_frog_limit_command: запрос от пользователя {user_id}")
        if not await self.admins_store.is_admin(user_id):
            self.logger.warning(f"set_frog_limit_command: пользователь {user_id} не является администратором")
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только администратору",
            )
            return
        if not context.args or len(context.args) < 1:
            self.logger.warning("set_frog_limit_command: аргументы не предоставлены")
            await self._safe_reply_with_fallback(
                update.message,
                f"📝 Использование: /set_frog_limit <threshold> (1..{MAX_FROG_THRESHOLD})",
            )
            return
        try:
            raw = int(context.args[0])
            self.logger.info(f"set_frog_limit_command: запрошенный порог: {raw}")
            if raw <= 0:
                raise ValueError(f"Порог должен быть положительным числом, получено: {raw}")
            result = await self._admin_command.set_frog_threshold(raw, max_threshold=MAX_FROG_THRESHOLD)
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    result.message,
                    max_retries=3,
                    delay=2,
                )
            except (TelegramError, NetworkError, TimedOut) as e:
                # Сетевые ошибки Telegram API
                self.logger.warning(f"Сетевая ошибка при отправке сообщения в set_frog_limit_command: {e}")
            except (ValueError, TypeError, AttributeError) as e:
                # Ошибки валидации данных
                self.logger.error(
                    f"Ошибка валидации при отправке сообщения в set_frog_limit_command: {e}", exc_info=True
                )
            except ServiceError as e:
                # Ошибки сервисного слоя
                self.logger.error(f"Ошибка сервиса при отправке сообщения в set_frog_limit_command: {e}", exc_info=True)
            # Критические ошибки (память, системные) должны пробрасываться выше
        except ValueError as e:
            self.logger.error(f"set_frog_limit_command: ошибка валидации параметра: {e}", exc_info=True)
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Неверный параметр. Использование: /set_frog_limit <threshold> (1..{MAX_FROG_THRESHOLD})",
                    max_retries=3,
                    delay=2,
                )
            except Exception as send_error:
                # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
                self.logger.error(
                    f"Не удалось отправить сообщение об ошибке после {3} попыток: {send_error}", exc_info=True
                )
        except (TelegramError, NetworkError, TimedOut) as e:
            # Сетевые ошибки Telegram API
            self.logger.warning(f"Сетевая ошибка в set_frog_limit_command: {e}")
        except ServiceError as e:
            # Ошибки сервисного слоя
            self.logger.error(f"Ошибка сервиса в set_frog_limit_command: {e}", exc_info=True)
            await self._safe_reply_text_with_error_logging(
                update.message,
                f"❌ Ошибка сервиса: {str(e)[:200]}",
                error_context="сообщение об ошибке сервиса",
                max_retries=3,
                delay=2,
            )
        except RepoError as e:
            # Ошибки репозитория
            self.logger.error(f"Ошибка репозитория в set_frog_limit_command: {e}", exc_info=True)
            await self._safe_reply_text_with_error_logging(
                update.message,
                f"❌ Ошибка доступа к данным: {str(e)[:200]}",
                error_context="сообщение об ошибке репозитория",
                max_retries=3,
                delay=2,
            )
            # Критические ошибки (память, системные) должны пробрасываться выше
            await self._safe_reply_text_with_error_logging(
                update.message,
                "❌ Произошла неожиданная ошибка при изменении лимита",
                error_context="сообщение об ошибке",
                max_retries=3,
                delay=2,
            )  # Если не удалось отправить, централизованный обработчик перехватит

    async def set_frog_used_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_frog_used.

        Устанавливает текущее значение выработки /frog за месяц.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, используемый для доступа к аргументам команды
                через context.args. Данные об использовании берутся из self.services.usage.

        Side Effects:
            - Вызывает usage.set_month_total() для установки текущего использования.
            - Отправляет ответное сообщение пользователю с информацией о лимитах.

        Raises:
            ValueError: Если переданный аргумент не является неотрицательным числом.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not await self.admins_store.is_admin(user_id):
            if not await self._safe_reply_text_with_error_logging(
                update.message,
                "❌ Доступно только администратору",
                error_context="сообщение об ограничении доступа",
                max_retries=3,
                delay=2,
            ):
                return
            return
        if not context.args or len(context.args) < 1:
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: /set_frog_used <count>",
            )
            return
        try:
            raw = int(context.args[0])
            if raw < 0:
                raise ValueError
            result = await self._admin_command.set_frog_used(raw)
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    result.message,
                    max_retries=3,
                    delay=2,
                )
            except (TelegramError, NetworkError, TimedOut) as e:
                # Сетевые ошибки Telegram API
                self.logger.warning(f"Сетевая ошибка при отправке сообщения в set_frog_used_command: {e}")
            except (ValueError, TypeError, AttributeError) as e:
                # Ошибки валидации данных
                self.logger.error(
                    f"Ошибка валидации при отправке сообщения в set_frog_used_command: {e}", exc_info=True
                )
            except ServiceError as e:
                # Ошибки сервисного слоя
                self.logger.error(f"Ошибка сервиса при отправке сообщения в set_frog_used_command: {e}", exc_info=True)
            # Критические ошибки (память, системные) должны пробрасываться выше
        except ValueError:
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Неверный параметр. Использование: /set_frog_used <count>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}", exc_info=True)

    async def mod_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /mod.

        Предоставляет административные права указанному пользователю.
        Команда доступна только главному администратору (Super Admin).

        Поддерживает два способа указания целевого пользователя:
        - Ответ на сообщение пользователя (reply)
        - Аргумент команды: /mod <user_id>

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args для получения user_id нового администратора.

        Side Effects:
            - Вызывает admins_store.add_admin() для добавления пользователя в список администраторов.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /mod от пользователя {user_id}")

        # Проверка прав: только главный администратор
        if not await self._admin_access.is_super_admin(user_id):
            self.logger.warning(f"mod_command: пользователь {user_id} не является главным администратором")
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только главному администратору",
            )
            return

        # Извлекаем target_user_id из reply или аргументов
        target_user_id = await self._extract_target_user_id(update, context)

        if target_user_id is None:
            self.logger.warning("mod_command: не удалось определить target_user_id")
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: ответьте на сообщение пользователя командой /mod или вызовите: /mod <user_id>",
            )
            return

        self.logger.info(f"mod_command: попытка добавить админа {target_user_id} пользователем {user_id}")

        # Добавляем администратора через AdminCommandService
        try:
            result = await self._admin_command.add_admin(
                target_user_id=target_user_id,
                requester_user_id=user_id,
            )
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    result.message,
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
                self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}", exc_info=True)
        except AccessDeniedError:
            # Должно быть обработано выше, но на всякий случай
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только главному администратору",
            )

    async def unmod_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /unmod.

        Удаляет административные права у указанного пользователя или показывает список админов.
        Главного администратора (из .env) удалить нельзя.
        Команда доступна только главному администратору (Super Admin).

        Поддерживает два режима:
        - Без аргументов/reply: показывает список всех администраторов
        - С reply или аргументом: удаляет админ-права у указанного пользователя

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args для получения user_id администратора для удаления.

        Side Effects:
            - Вызывает admins_store.remove_admin() для удаления пользователя из списка администраторов.
            - Вызывает admins_store.list_all_admins() для получения списка администраторов.
            - Вызывает context.bot.get_chat() для получения информации о пользователях.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /unmod от пользователя {user_id}")

        # Проверка прав: только главный администратор
        if not await self._admin_access.is_super_admin(user_id):
            self.logger.warning(f"unmod_command: пользователь {user_id} не является главным администратором")
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только главному администратору",
            )
            return

        # Извлекаем target_user_id из reply или аргументов
        target_user_id = await self._extract_target_user_id(update, context)

        # Если target_user_id не определён - показываем список админов
        if target_user_id is None:
            self.logger.info("unmod_command: target_user_id не определён, показываем список админов")
            try:
                admins = await self._admin_command.list_all_admins()
                if not admins:
                    try:
                        await retry_on_connect_error(
                            update.message.reply_text,
                            "📭 Нет администраторов",
                            max_retries=3,
                            delay=2,
                        )
                    except Exception as e:
                        # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
                        self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}", exc_info=True)
                    return

                # Получаем информацию об администраторах через chat_info_service
                from app.admin_notification_builders import AdminInfo, AdminNotificationBuilders

                admin_infos: list[AdminInfo] = []

                if self._chat_info_service:
                    for admin_id in admins:
                        is_super = await self._admin_access.is_super_admin(admin_id)
                        try:
                            chat_details = await self._chat_info_service.get_chat_details_safe(admin_id)
                            if chat_details:
                                name_raw = (
                                    chat_details.get("title")
                                    or chat_details.get("first_name")
                                    or chat_details.get("full_name")
                                    or "Unknown"
                                )
                                name = str(name_raw) if name_raw is not None else "Unknown"
                                username_raw = chat_details.get("username")
                                username = str(username_raw) if username_raw is not None else None
                            else:
                                name = "Unknown"
                                username = None
                        except Exception:
                            name = "Unknown"
                            username = None

                        admin_infos.append(
                            AdminInfo(
                                admin_id=admin_id,
                                name=name,
                                username=username,
                                is_super_admin=is_super,
                            )
                        )
                else:
                    # Fallback без chat_info_service
                    for admin_id in admins:
                        is_super = await self._admin_access.is_super_admin(admin_id)
                        admin_infos.append(
                            AdminInfo(
                                admin_id=admin_id,
                                name="Unknown",
                                username=None,
                                is_super_admin=is_super,
                            )
                        )

                message = AdminNotificationBuilders.build_admin_list_message(admin_infos)
                try:
                    await retry_on_connect_error(
                        update.message.reply_text,
                        message,
                        max_retries=3,
                        delay=2,
                    )
                    self.logger.info(f"Отправлен список из {len(admins)} администраторов пользователю {user_id}")
                except Exception as e:
                    # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
                    self.logger.error(f"Не удалось отправить список админов после {3} попыток: {e}", exc_info=True)
                    try:
                        await retry_on_connect_error(
                            update.message.reply_text,
                            "❌ Ошибка при отправке списка администраторов",
                            max_retries=3,
                            delay=2,
                        )
                    except Exception as fallback_error:
                        # Обрабатываем ошибку отправки fallback сообщения
                        self._handle_send_message_error(
                            fallback_error,
                            context="отправке сообщения об ошибке отправки списка админов",
                        )
            except Exception as e:
                # Неожиданные ошибки при получении списка админов
                self.logger.error(f"Ошибка при получении списка админов: {e}", exc_info=True)
                try:
                    await retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Ошибка при получении списка администраторов",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as error_error:
                    # Обрабатываем ошибку отправки сообщения об ошибке
                    self._handle_send_message_error(
                        error_error,
                        context="отправке сообщения об ошибке получения списка админов",
                    )
            return

        # Ветка удаления админа
        self.logger.info(f"unmod_command: попытка удалить админа {target_user_id} пользователем {user_id}")

        # Удаляем админа через AdminCommandService
        try:
            # Получаем super_admin_id через admin_access_service
            super_admin_id = self._admin_access.get_super_admin_id()

            result = await self._admin_command.remove_admin(
                target_user_id=target_user_id,
                requester_user_id=user_id,
                super_admin_id=super_admin_id,
            )
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    result.message,
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
                self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}", exc_info=True)
        except AccessDeniedError:
            # Должно быть обработано выше, но на всякий случай
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только главному администратору",
            )
        except ServiceError as e:
            # Ошибка при попытке удалить главного админа
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception as service_error:
                # Обрабатываем ошибку отправки сообщения об ошибке сервиса
                self._handle_send_message_error(
                    service_error,
                    context="отправке сообщения об ошибке сервиса при удалении админа",
                )

    async def list_mods_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /list_mods.

        Возвращает список всех администраторов бота с их ID.
        Главный администратор (из .env) помечается специальной пометкой.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Вызывает admins_store.list_all_admins() для получения списка администраторов.
            - Отправляет форматированный список администраторов пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /list_mods от пользователя {user_id}")

        if not await self.admins_store.is_admin(user_id):
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Доступно только администратору",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(
                    f"Не удалось отправить сообщение об ограничении доступа после {3} попыток: {e}", exc_info=True
                )
            return

        all_admins = await self._admin_command.list_all_admins()
        if not all_admins:
            self.logger.info("Нет администраторов")
            await self._safe_reply_with_fallback(
                update.message,
                "📭 Нет администраторов",
            )
            return

        # Используем билдер для форматирования сообщения
        from app.admin_notification_builders import AdminNotificationBuilders

        super_admin_id = self._admin_access.get_super_admin_id()
        message = AdminNotificationBuilders.build_simple_admin_list_message(
            admins=all_admins,
            super_admin_id=super_admin_id,
        )
        try:
            await retry_on_connect_error(
                update.message.reply_text,
                message,
                max_retries=3,
                delay=2,
            )
            self.logger.info(f"Отправлен список из {len(all_admins)} администраторов пользователю {user_id}")
        except Exception as e:
            # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
            self.logger.error(f"Не удалось отправить список админов после {3} попыток: {e}", exc_info=True)
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Ошибка при отправке списка администраторов",
                    max_retries=3,
                    delay=2,
                )
            except Exception as list_error:
                # Обрабатываем ошибку отправки сообщения об ошибке
                self._handle_send_message_error(
                    list_error,
                    context="отправке сообщения об ошибке отправки списка админов",
                )
