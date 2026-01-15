from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.admin_notification_builders import AdminNotificationBuilders
from bot.handlers.base import (
    BaseHandlers,
)
from bot.handlers.messages import (
    SUPER_ADMIN_ACCESS_DENIED,
)
from shared.base.exceptions import (
    AccessDeniedError,
    ServiceError,
)
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger
from shared.retry import retry_on_connect_error

# Константы
MAX_FROG_THRESHOLD = 100  # максимальный порог ручных генераций


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
        if not await self._check_admin_access(user_id, update.message):
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

        if not await self._check_admin_access(user_id, update.message):
            return

        # Без аргументов - показываем список чатов
        if not self._has_args(context):
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

        if not await self._check_admin_access(update.effective_user.id, update.message):
            return

        if not self._has_args(context):
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: /add_chat <chat_id>",
            )
            return

        try:
            chat_id = int(context.args[0])
            # Валидация через сервис
            validation_result = self._admin_command.validate_chat_id(chat_id)
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

        if not await self._check_admin_access(update.effective_user.id, update.message):
            return

        if not self._has_args(context):
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: /remove_chat <chat_id>",
            )
            return

        try:
            chat_id = int(context.args[0])
            # Валидация через сервис
            validation_result = self._admin_command.validate_chat_id(chat_id)
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

        if not await self._check_admin_access(user_id, update.message):
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
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /set_frog_limit от пользователя {user_id}")

        if not await self._check_admin_access(user_id, update.message):
            return

        if not self._has_args(context):
            await self._safe_reply_with_fallback(
                update.message,
                f"📝 Использование: /set_frog_limit <threshold> (1..{MAX_FROG_THRESHOLD})",
            )
            return

        async def _execute() -> None:
            raw = int(context.args[0])
            if raw <= 0:
                raise ValueError(f"Порог должен быть положительным числом, получено: {raw}")
            result = await self._admin_command.set_frog_threshold(raw, max_threshold=MAX_FROG_THRESHOLD)
            await self._safe_reply_with_fallback(update.message, result.message)

        await self._handle_command_errors(update, _execute)

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
        if not await self._check_admin_access(user_id, update.message):
            return

        if not self._has_args(context):
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: /set_frog_used <count>",
            )
            return

        async def _execute() -> None:
            raw = int(context.args[0])
            if raw < 0:
                raise ValueError(f"Количество использований должно быть неотрицательным числом, получено: {raw}")
            result = await self._admin_command.set_frog_used(raw)
            await self._safe_reply_with_fallback(update.message, result.message)

        await self._handle_command_errors(update, _execute)

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
        if not await self._check_admin_access(user_id, update.message, require_super=True):
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
                SUPER_ADMIN_ACCESS_DENIED,
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
        if not await self._check_admin_access(user_id, update.message, require_super=True):
            return

        # Извлекаем target_user_id из reply или аргументов
        target_user_id = await self._extract_target_user_id(update, context)

        # Если target_user_id не определён - показываем список админов
        if target_user_id is None:
            self.logger.info("unmod_command: target_user_id не определён, показываем список админов")
            try:
                result = await self._admin_command.get_admin_list_with_details()
                await self._safe_reply_with_fallback(
                    update.message,
                    result.message,
                )
                if result.success:
                    self.logger.info(f"Отправлен список администраторов пользователю {user_id}")
            except ServiceError as e:
                self.logger.error(
                    f"Ошибка сервиса при получении списка админов: {e}",
                    exc_info=True,
                )
                await self._safe_reply_with_fallback(
                    update.message,
                    f"❌ Ошибка сервиса: {str(e)[:200]}",
                )
            except Exception as e:
                # Неожиданные ошибки при получении списка админов
                self.logger.error(f"Ошибка при получении списка админов: {e}", exc_info=True)
                await self._safe_reply_with_fallback(
                    update.message,
                    "❌ Ошибка при получении списка администраторов",
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
                SUPER_ADMIN_ACCESS_DENIED,
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

        if not await self._check_admin_access(user_id, update.message):
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
