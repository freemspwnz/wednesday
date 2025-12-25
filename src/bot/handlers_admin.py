from __future__ import annotations

from telegram import Bot, Chat, Update, User
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from bot.base_handlers import (
    CHAT_INFO_TIMEOUT_DEFAULT,
    CHAT_TIMEOUT_DEFAULT,
    BaseHandlers,
)
from shared.base.exceptions import (
    AccessDeniedError,
    RepoError,
    ServiceError,
)
from shared.bot_services import BotServices, SupportBotServices, require_bot_services
from shared.protocols import ILogger
from shared.retry import retry_on_connect_error

# Константы
MAX_FROG_THRESHOLD = 100  # максимальный порог ручных генераций
MAX_ERROR_DETAILS_LENGTH = 500  # максимальная длина деталей ошибки
PERCENT_MULTIPLIER = 100  # множитель для процентов
MAX_LOG_DAYS = 10  # максимальное количество дней для команды /log
TELEGRAM_SAFE_MESSAGE_LENGTH = 4000  # безопасная длина для обрезки сообщений


class AdminHandlers(BaseHandlers):
    """Обработчики административных команд бота.

    Инкапсулирует команды управления ботом, логами, чатами и администраторами.
    Содержит полную реализацию всех административных команд.
    """

    def __init__(
        self,
        services: BotServices | SupportBotServices,
        logger: ILogger,
    ) -> None:
        super().__init__(services, logger)
        # Валидация типа: AdminHandlers работает только с BotServices
        self.services: BotServices = require_bot_services(services, "AdminHandlers")
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
    ) -> tuple[int, str]:
        """Безопасно получает информацию о чате с обработкой ошибок.

        Делегирует выполнение в ChatInfoService для соблюдения архитектурных границ.

        Args:
            bot: Экземпляр Telegram бота (не используется, оставлен для обратной совместимости).
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах.

        Returns:
            Кортеж (chat_id, title), где title - название чата или сообщение об ошибке.
        """
        return await self._chat_info_service.get_chat_info_safe(chat_id, timeout)

    async def _get_chat_safe(
        self,
        bot: Bot,
        chat_id: int,
        timeout: float = 10.0,
    ) -> Chat | None:
        """Безопасно получает полный объект чата с обработкой ошибок и таймаутом.

        Делегирует выполнение в ChatInfoService для соблюдения архитектурных границ.

        Args:
            bot: Экземпляр Telegram бота (не используется, оставлен для обратной совместимости).
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах (по умолчанию 10 секунд).

        Returns:
            Объект чата или None в случае ошибки.
        """
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

            success = await self._safe_reply_with_fallback(
                update.message,
                status_message,
                fallback_text="❌ Ошибка при получении статуса",
            )
            if success:
                self.logger.info("Отправлен статус бота")

        await self._handle_command_errors(update, _execute_status)

    async def admin_log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /log.

        Отправляет логи администратору. Без аргумента отправляет последний файл,
        с аргументом [count] отправляет логи за N дней (1..10).
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к боту для отправки файлов через context.bot.

        Side Effects:
            - Читает файлы логов из директории logs/.
            - Отправляет файлы логов в чат через context.bot.send_document().
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        await self._send_logs_command(update, context, max_days=MAX_LOG_DAYS)

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /stop.

        Останавливает бота полностью. Команда доступна только администраторам.
        После выполнения команды основной бот останавливается и запускается
        SupportBot для обслуживания резервных функций.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args.

        Side Effects:
            - Сохраняет метаданные сообщения для последующего редактирования.
            - Вызывает bot_controller.stop() для остановки основного бота через DI.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /stop от пользователя {user_id}")

        # Проверка прав администратора
        if not await self.admins_store.is_admin(user_id):
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Доступно только администратору",
            )
            return

        async def _execute_stop() -> None:
            # Получаем экземпляр основного бота через DI и останавливаем его
            bot_controller = self.services.bot_controller
            if bot_controller is not None:
                await bot_controller.stop()
            else:
                self.logger.error("bot_controller не доступен, невозможно остановить бота")
                await self._safe_reply_with_fallback(
                    update.message,
                    "❌ Ошибка: невозможно остановить бота (bot_controller недоступен)",
                )

        await self._handle_command_errors(update, _execute_stop)

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

        chat_ids = await self._admin_command.list_chat_ids()
        if not chat_ids:
            self.logger.info("Нет активных чатов")
            await self._safe_reply_with_fallback(
                update.message,
                "📭 Нет активных чатов для отправки",
            )
            return

        # Если аргумент не передан - показываем список чатов
        if not context.args or len(context.args) == 0:
            # Получаем информацию о чатах параллельно для улучшения производительности
            tasks = [self._get_chat_info_safe(context.bot, chat_id) for chat_id in chat_ids]
            results: list[tuple[int, str] | BaseException] = await self._gather_with_timeout(
                *tasks,
                timeout=CHAT_INFO_TIMEOUT_DEFAULT,
                return_exceptions=True,
            )

            chat_list = []
            for result in results:
                if isinstance(result, BaseException):
                    self.logger.warning(f"Ошибка при получении информации о чате: {result}")
                    chat_list.append(f"• Чат (ошибка: {type(result).__name__})")
                else:
                    chat_id, title = result
                    chat_list.append(f"• {title} (ID: {chat_id})")

            message = (
                "📋 Активные чаты для отправки:\n\n"
                + "\n".join(chat_list)
                + "\n\n"
                + "💡 Использование:\n"
                + "• /force_send <chat_id> — отправить жабу в указанный чат\n"
                + "• /force_send all — отправить жабу во все чаты"
            )
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    message,
                    max_retries=3,
                    delay=2,
                )
                self.logger.info(f"Отправлен список из {len(chat_ids)} активных чатов пользователю {user_id}")
            except (TelegramError, NetworkError, TimedOut) as e:
                self.logger.error(f"Не удалось отправить список чатов после {3} попыток: {e}")
            return

        # Получаем аргумент
        arg = context.args[0].strip().lower()

        # Проверяем лимит генераций
        usage = self.services.usage
        can_generate = True
        if usage:
            can_generate = await usage.can_use_frog()
            if not can_generate:
                total, threshold, quota = await usage.get_limits_info()
                self.logger.info(
                    f"Лимит ручных генераций исчерпан: {total}/{quota}, порог: {threshold}",
                )

        # Определяем целевые чаты
        target_chat_ids: list[int] = []
        if arg == "all":
            target_chat_ids = list(chat_ids)
        else:
            try:
                requested_chat_id = int(arg)
                if requested_chat_id in chat_ids:
                    target_chat_ids = [requested_chat_id]
                else:
                    await self._safe_reply_with_fallback(
                        update.message,
                        f"❌ Чат {requested_chat_id} не найден в списке активных чатов",
                    )
                    return
            except ValueError:
                await self._safe_reply_with_fallback(
                    update.message,
                    "❌ Неверный аргумент. Используйте: /force_send <chat_id> или /force_send all",
                )
                return

        if not target_chat_ids:
            await self._safe_reply_with_fallback(
                update.message,
                "❌ Нет целевых чатов для отправки",
            )
            return

        # Отправляем статусное сообщение
        try:
            status_msg = await retry_on_connect_error(
                update.message.reply_text,
                f"🔄 Генерирую и отправляю жабу в {len(target_chat_ids)} чат(ов)...",
                max_retries=3,
                delay=2,
            )
        except (TelegramError, NetworkError, TimedOut) as e:
            self.logger.error(f"Не удалось отправить статусное сообщение после {3} попыток: {e}")
            status_msg = None

        # Генерируем или получаем изображение
        image_data: bytes | None = None
        caption: str = ""
        use_fallback = False

        image_service = self.services.image_service
        if can_generate and image_service is not None:
            # Используем централизованный метод обработки ошибок генерации изображений
            image_data, caption, use_fallback = await self._handle_image_generation_errors(
                image_service=image_service,
                user_id=user_id,
            )
            # Увеличиваем счетчик использования только если генерация успешна
            if not use_fallback and usage:
                await usage.increment(1)
        else:
            use_fallback = True
            self.logger.info("Лимит генераций исчерпан, используем fallback")

        # Если нужно использовать fallback и изображение еще не получено
        if use_fallback and image_data is None:
            if image_service is not None:
                fallback_image = await image_service.get_random_saved_image()
            else:
                fallback_image = None
            if fallback_image:
                image_data, caption = fallback_image
                self.logger.info("Используется случайное изображение из архива")
            else:
                self.logger.warning("Нет сохраненных изображений для отправки")
                await self._safe_reply_text_with_error_logging(
                    update.message,
                    "❌ Не удалось получить изображение (лимит исчерпан и нет сохраненных изображений)",
                    error_context="сообщение об ошибке",
                    max_retries=3,
                    delay=2,
                )
                await self._safe_delete_message(status_msg)
                return

        if not image_data:
            self.logger.error("Не удалось получить изображение для отправки")
            await self._safe_reply_text_with_error_logging(
                update.message,
                "❌ Не удалось получить изображение для отправки",
                error_context="сообщение об ошибке",
                max_retries=3,
                delay=2,
            )
            await self._safe_delete_message(status_msg)
            return

        # Отправляем изображение главному админу
        admin_chat_id = self.services.settings.admin_chat_id
        if admin_chat_id:
            try:
                await retry_on_connect_error(
                    context.bot.send_photo,
                    chat_id=admin_chat_id,
                    photo=image_data,
                    caption=f"🐸 Принудительная отправка (команда /force_send)\n\n{caption}",
                    max_retries=3,
                    delay=2,
                )
                self.logger.info(f"Изображение отправлено главному админу {admin_chat_id}")
            except (TelegramError, NetworkError, TimedOut) as e:
                # Сетевые ошибки - отправка админу не критична, продолжаем работу
                self.logger.warning(f"Сетевая ошибка при отправке изображения главному админу: {e}")
            except (ValueError, TypeError, AttributeError) as e:
                # Ошибки валидации данных
                self.logger.warning(f"Ошибка валидации при отправке изображения главному админу: {e}", exc_info=True)
            except ServiceError as e:
                # Ошибки сервисного слоя
                self.logger.warning(f"Ошибка сервиса при отправке изображения главному админу: {e}", exc_info=True)
            # Критические ошибки (память, системные) должны пробрасываться выше

        # Отправляем изображение в целевые чаты
        success_count = 0
        failed_count = 0
        for target_chat_id in target_chat_ids:
            try:
                await retry_on_connect_error(
                    context.bot.send_photo,
                    chat_id=target_chat_id,
                    photo=image_data,
                    caption=caption,
                    max_retries=3,
                    delay=2,
                )
                success_count += 1
                self.logger.info(f"Изображение отправлено в чат {target_chat_id}")
            except (TelegramError, NetworkError, TimedOut) as e:
                # Сетевые ошибки - ошибка отправки в один чат не должна прерывать отправку в другие
                failed_count += 1
                self.logger.warning(f"Сетевая ошибка при отправке изображения в чат {target_chat_id}: {e}")
            except (ValueError, TypeError, AttributeError) as e:
                # Ошибки валидации данных
                failed_count += 1
                self.logger.warning(
                    f"Ошибка валидации при отправке изображения в чат {target_chat_id}: {e}", exc_info=True
                )
            except ServiceError as e:
                # Ошибки сервисного слоя
                failed_count += 1
                self.logger.warning(
                    f"Ошибка сервиса при отправке изображения в чат {target_chat_id}: {e}", exc_info=True
                )
            # Критические ошибки (память, системные) должны пробрасываться выше

        # Удаляем статусное сообщение и отправляем итоговое
        await self._safe_delete_message(status_msg)

        result_message = (
            f"✅ Отправка выполнена:\n"
            f"• Успешно: {success_count}/{len(target_chat_ids)}\n"
            f"• Ошибок: {failed_count}\n"
            f"• Использован: {'fallback (лимит исчерпан)' if use_fallback else 'новая генерация'}"
        )
        if await self._safe_reply_text_with_error_logging(
            update.message,
            result_message,
            error_context="итоговое сообщение",
            max_retries=3,
            delay=2,
        ):
            self.logger.info(f"Команда /force_send выполнена: {success_count} успешных отправок")

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
            # Валидация диапазона: Telegram chat_id может быть положительным (пользователи)
            # или отрицательным (группы/каналы, начинаются с -100)
            # Максимальное значение для int64: 2**63 - 1, минимальное: -2**63
            if chat_id < -(2**63) or chat_id > 2**63 - 1:
                raise ValueError("chat_id выходит за допустимый диапазон")
            if chat_id == 0:
                raise ValueError("chat_id не может быть нулем")

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
            # Валидация диапазона: Telegram chat_id может быть положительным (пользователи)
            # или отрицательным (группы/каналы, начинаются с -100)
            # Максимальное значение для int64: 2**63 - 1, минимальное: -2**63
            if chat_id < -(2**63) or chat_id > 2**63 - 1:
                raise ValueError("chat_id выходит за допустимый диапазон")
            if chat_id == 0:
                raise ValueError("chat_id не может быть нулем")

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

        chat_ids = await self._admin_command.list_chat_ids()
        if not chat_ids:
            self.logger.info("Нет активных чатов")
            if not await self._safe_reply_text_with_error_logging(
                update.message,
                "📭 Нет активных чатов",
                error_context="сообщение",
                max_retries=3,
                delay=2,
            ):
                return
            return

        # Получаем информацию о чатах параллельно для улучшения производительности
        tasks = [self._get_chat_info_safe(context.bot, chat_id) for chat_id in chat_ids]
        results: list[tuple[int, str] | BaseException] = await self._gather_with_timeout(
            *tasks,
            timeout=CHAT_INFO_TIMEOUT_DEFAULT,
            return_exceptions=True,
        )

        chat_list = []
        for result in results:
            if isinstance(result, BaseException):
                self.logger.warning(f"Ошибка при получении информации о чате: {result}")
                chat_list.append(f"• Чат (ошибка: {type(result).__name__})")
            else:
                chat_id, title = result
                chat_list.append(f"• {title} (ID: {chat_id})")

        async def _execute_list_chats() -> None:
            message = "📋 Активные чаты:\n\n" + "\n".join(chat_list)
            success = await self._safe_reply_with_fallback(
                update.message,
                message,
            )
            if success:
                self.logger.info(f"Отправлен список из {len(chat_ids)} активных чатов пользователю {user_id}")

        await self._handle_command_errors(update, _execute_list_chats)

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

                # Получаем информацию об администраторах параллельно для улучшения производительности
                tasks = [self._get_chat_safe(context.bot, admin_id) for admin_id in admins]
                chat_results: list[object | None | BaseException] = await self._gather_with_timeout(
                    *tasks,
                    timeout=CHAT_TIMEOUT_DEFAULT,
                    return_exceptions=True,
                )

                admin_list = []
                for admin_id, chat in zip(admins, chat_results, strict=True):
                    # Помечаем главного админа (нужно получить независимо от результата запроса)
                    is_main = " (главный)" if await self._admin_access.is_super_admin(admin_id) else ""

                    if isinstance(chat, BaseException) or chat is None:
                        self.logger.warning(f"Не удалось получить информацию об администраторе {admin_id}")
                        admin_list.append(f"• ID: {admin_id} (не удалось получить информацию){is_main}")
                        continue

                    # Формируем имя с разумным fallback
                    # Используем проверку типов вместо hasattr для лучшей типизации
                    if isinstance(chat, User):
                        # User имеет свойство full_name, которое объединяет first_name и last_name
                        name = chat.full_name or chat.first_name or "Unknown"
                        username_text = f" (@{chat.username})" if chat.username else ""
                    elif isinstance(chat, Chat):
                        # Chat для пользователя имеет first_name, last_name, но не full_name
                        name_parts = []
                        if chat.first_name:
                            name_parts.append(chat.first_name)
                        if chat.last_name:
                            name_parts.append(chat.last_name)
                        # Для Chat также может быть title (для групп/каналов)
                        name = " ".join(name_parts) if name_parts else (chat.title or "Unknown")
                        username_text = f" (@{chat.username})" if chat.username else ""
                    else:
                        # Fallback для неизвестных типов
                        name = "Unknown"
                        username_text = ""

                    admin_list.append(f"• ID: {admin_id} ({name}{username_text}){is_main}")

                message = "👥 Список администраторов:\n\n" + "\n".join(admin_list)
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
                    except Exception:
                        # Exception с pass оправдан - если не удалось отправить, централизованный обработчик перехватит
                        pass
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
                except Exception:
                    # Exception с pass оправдан - если не удалось отправить, централизованный обработчик перехватит
                    pass
            return

        # Ветка удаления админа
        self.logger.info(f"unmod_command: попытка удалить админа {target_user_id} пользователем {user_id}")

        # Удаляем админа через AdminCommandService
        try:
            super_admin_id = None
            if self.services.settings.admin_chat_id:
                try:
                    super_admin_id = int(self.services.settings.admin_chat_id)
                except (ValueError, TypeError):
                    pass

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
            except Exception:
                # Exception с pass оправдан - если не удалось отправить, централизованный обработчик перехватит
                pass

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

        admin_list = []
        main_admin = self.services.settings.admin_chat_id
        for admin_id in all_admins:
            is_main = " (главный)" if (main_admin and main_admin == admin_id) else ""
            admin_list.append(f"• ID: {admin_id}{is_main}")

        message = "👥 Список администраторов:\n\n" + "\n".join(admin_list)
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
            except Exception:
                # Exception с pass оправдан - если не удалось отправить, централизованный обработчик перехватит
                pass  # Если не удалось отправить, централизованный обработчик перехватит
