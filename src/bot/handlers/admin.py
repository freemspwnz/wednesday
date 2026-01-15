from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import (
    BaseHandlers,
)
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger


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
                для получения информации о боте.

        Side Effects:
            - Вызывает admin_dashboard_service.build_status_message() для получения статуса.
            - Отправляет подробный статус пользователю.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /status от пользователя {user_id}")

        # Проверка доступа администратора
        if not await self._check_admin_access(user_id, message):
            return

        async def _execute_status() -> None:
            status_message = await self._dashboard_service.build_status_message()

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

        Side Effects:
            - Делегирует выполнение команды в admin_command_service.execute_force_send().
            - Отправляет результат выполнения пользователю.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /force_send от пользователя {user_id}")

        if not await self._check_admin_access(user_id, message):
            return

        # Без аргументов - показываем список чатов
        if not self._has_args(context):
            result = await self._admin_command.get_chat_list_for_display()
            await self._safe_reply_with_fallback(
                message,
                result.message,
            )
            return

        # Передаем сырой аргумент - нормализация будет в сервисе
        raw_arg = context.args[0]

        # Делегируем всю бизнес-логику в сервис (включая нормализацию и обработку ошибок)
        result = await self._admin_command.execute_force_send(
            requester_user_id=user_id,
            target_arg=raw_arg,
        )
        await self._safe_reply_with_fallback(
            message,
            result.message,
        )
        if result.success:
            self.logger.info(f"Команда /force_send выполнена пользователем {user_id}")

    async def admin_add_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /add_chat.

        Добавляет чат в список рассылки для автоматических отправок.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args.

        Side Effects:
            - Делегирует добавление чата в admin_command_service.add_chat_from_string().
            - Отправляет ответное сообщение пользователю с результатом операции.

        Raises:
            ValueError: Если переданный chat_id не является числом.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        if not await self._check_admin_access(user.id, message):
            return

        if not self._has_args(context):
            usage_message = self._admin_command.get_add_chat_usage_message()
            await self._safe_reply_with_fallback(
                message,
                usage_message,
            )
            return

        async def _execute() -> None:
            # Передаем сырой аргумент - нормализация будет в сервисе
            raw_arg = context.args[0]
            result = await self._admin_command.add_chat_from_string(raw_arg, "Manually added")
            if result.success:
                self.logger.info("Чат успешно добавлен в рассылку")
            else:
                self.logger.warning(f"Не удалось добавить чат: {result.message}")
            await self._safe_reply_with_fallback(message, result.message)

        await self._handle_command_errors(update, _execute)

    async def admin_remove_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /remove_chat.

        Удаляет чат из списка рассылки для автоматических отправок.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args.

        Side Effects:
            - Делегирует удаление чата в admin_command_service.remove_chat_from_string().
            - Отправляет ответное сообщение пользователю с результатом операции.

        Raises:
            ValueError: Если переданный chat_id не является числом.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        if not await self._check_admin_access(user.id, message):
            return

        if not self._has_args(context):
            usage_message = self._admin_command.get_remove_chat_usage_message()
            await self._safe_reply_with_fallback(
                message,
                usage_message,
            )
            return

        async def _execute() -> None:
            # Передаем сырой аргумент - нормализация будет в сервисе
            raw_arg = context.args[0]
            result = await self._admin_command.remove_chat_from_string(raw_arg)
            if result.success:
                self.logger.info("Чат успешно удалён из рассылки")
            else:
                self.logger.warning(f"Не удалось удалить чат: {result.message}")
            await self._safe_reply_with_fallback(message, result.message)

        await self._handle_command_errors(update, _execute)

    async def list_chats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /list_chats.

        Возвращает список всех активных чатов с их ID и названиями.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Делегирует получение и форматирование списка чатов в admin_command_service.get_chat_list_for_display().
            - Отправляет форматированный список чатов пользователю.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /list_chats от пользователя {user_id}")

        if not await self._check_admin_access(user_id, message):
            return

        # Делегируем получение и форматирование списка чатов в сервис
        result = await self._admin_command.get_chat_list_for_display()
        await self._safe_reply_with_fallback(
            message,
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
                через context.args.

        Side Effects:
            - Делегирует установку порога в admin_command_service.set_frog_threshold_from_string().
            - Отправляет ответное сообщение пользователю с результатом операции.

        Raises:
            ValueError: Если переданный аргумент не является положительным числом.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /set_frog_limit от пользователя {user_id}")

        if not await self._check_admin_access(user_id, message):
            return

        if not self._has_args(context):
            usage_message = self._admin_command.get_set_frog_limit_usage_message()
            await self._safe_reply_with_fallback(
                message,
                usage_message,
            )
            return

        async def _execute() -> None:
            # Передаем сырой аргумент - нормализация будет в сервисе
            raw_arg = context.args[0]
            result = await self._admin_command.set_frog_threshold_from_string(raw_arg)
            await self._safe_reply_with_fallback(message, result.message)

        await self._handle_command_errors(update, _execute)

    async def set_frog_used_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_frog_used.

        Устанавливает текущее значение выработки /frog за месяц.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, используемый для доступа к аргументам команды
                через context.args.

        Side Effects:
            - Делегирует установку использования в admin_command_service.set_frog_used_from_string().
            - Отправляет ответное сообщение пользователю с информацией о лимитах.

        Raises:
            ValueError: Если переданный аргумент не является неотрицательным числом.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        if not await self._check_admin_access(user_id, message):
            return

        if not self._has_args(context):
            usage_message = self._admin_command.get_set_frog_used_usage_message()
            await self._safe_reply_with_fallback(
                message,
                usage_message,
            )
            return

        async def _execute() -> None:
            # Передаем сырой аргумент - нормализация будет в сервисе
            raw_arg = context.args[0]
            result = await self._admin_command.set_frog_used_from_string(raw_arg)
            await self._safe_reply_with_fallback(message, result.message)

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
            - Делегирует добавление администратора в admin_command_service.add_admin().
            - Отправляет ответное сообщение пользователю с результатом операции.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /mod от пользователя {user_id}")

        # Проверка прав: только главный администратор
        if not await self._check_admin_access(user_id, message, require_super=True):
            return

        # Извлекаем target_user_id из reply или аргументов
        target_user_id = await self._extract_target_user_id(update, context)

        if target_user_id is None:
            self.logger.warning("mod_command: не удалось определить target_user_id")
            usage_message = self._admin_command.get_mod_usage_message()
            await self._safe_reply_with_fallback(
                message,
                usage_message,
            )
            return

        self.logger.info(f"mod_command: попытка добавить админа {target_user_id} пользователем {user_id}")

        # Добавляем администратора через AdminCommandService
        # Сервис обрабатывает все исключения и возвращает готовое сообщение
        result = await self._admin_command.add_admin(
            target_user_id=target_user_id,
            requester_user_id=user_id,
        )
        await self._safe_reply_with_fallback(
            message,
            result.message,
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
            - Делегирует удаление администратора в admin_command_service.remove_admin().
            - Делегирует получение списка администраторов в admin_command_service.get_admin_list_with_details().
            - Отправляет ответное сообщение пользователю с результатом операции.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /unmod от пользователя {user_id}")

        # Проверка прав: только главный администратор
        if not await self._check_admin_access(user_id, message, require_super=True):
            return

        # Извлекаем target_user_id из reply или аргументов
        target_user_id = await self._extract_target_user_id(update, context)

        # Если target_user_id не определён - показываем список админов
        if target_user_id is None:
            self.logger.info("unmod_command: target_user_id не определён, показываем список админов")
            # Сервис обрабатывает все исключения и возвращает готовое сообщение
            result = await self._admin_command.get_admin_list_with_details()
            await self._safe_reply_with_fallback(
                message,
                result.message,
            )
            if result.success:
                self.logger.info(f"Отправлен список администраторов пользователю {user_id}")
            return

        # Ветка удаления админа
        self.logger.info(f"unmod_command: попытка удалить админа {target_user_id} пользователем {user_id}")

        # Удаляем админа через AdminCommandService
        # Сервис обрабатывает все исключения и возвращает готовое сообщение
        result = await self._admin_command.remove_admin(
            target_user_id=target_user_id,
            requester_user_id=user_id,
        )
        await self._safe_reply_with_fallback(
            message,
            result.message,
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
            - Делегирует получение списка администраторов в admin_command_service.get_admin_list_with_details().
            - Отправляет форматированный список администраторов пользователю.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /list_mods от пользователя {user_id}")

        if not await self._check_admin_access(user_id, message):
            return

        result = await self._admin_command.get_admin_list_with_details()
        await self._safe_reply_with_fallback(
            message,
            result.message,
        )
        if result.success:
            self.logger.info(f"Отправлен список администраторов пользователю {user_id}")
