from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BaseHandlers
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger


class ModelHandlers(BaseHandlers):
    """Обработчики команд управления моделями (Kandinsky и GigaChat).

    Инкапсулирует команды выбора и перечисления моделей генерации изображений
    и текстового клиента. Содержит полную реализацию всех модельных команд.
    """

    def __init__(
        self,
        services: BotServices,
        logger: ILogger,
    ) -> None:
        super().__init__(services, logger)
        # Используем ModelManagementService для управления моделями
        if self.services.admin_dashboard_service is None:
            raise ValueError("admin_dashboard_service must be provided in BotServices")
        if self.services.model_management_service is None:
            raise ValueError("model_management_service must be provided in BotServices")
        if self.services.admin_access_service is None:
            raise ValueError("admin_access_service must be provided in BotServices")
        self._dashboard_service = self.services.admin_dashboard_service
        self._model_management_service = self.services.model_management_service
        self._admin_access = self.services.admin_access_service

    async def set_kandinsky_model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_kandinsky_model.

        Устанавливает модель Kandinsky для генерации изображений.
        Можно указать как pipeline_id (число), так и название модели.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
            и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args. Клиент изображения берётся из image_client.

        Side Effects:
            - Вызывает image_generator.image_client.set_model() для установки модели.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        if not await self._check_admin_access(update.effective_user.id, update.message):
            return

        if not self._has_args(context):
            await self._safe_reply_with_fallback(
                update.message,
                (
                    "📝 Использование: /set_kandinsky_model <pipeline_id или название модели>\n\n"
                    "Используйте /list_models для просмотра доступных моделей.\n"
                    "Можно указать как ID (например: 12345678), так и название модели (например: kandinsky-2.2)"
                ),
            )
            return

        model_arg = " ".join(context.args)  # Объединяем аргументы на случай названий с пробелами
        await self._safe_reply_with_fallback(
            update.message,
            "⏳ Устанавливаю модель...",
        )

        async def _execute() -> None:
            result = await self._model_management_service.set_kandinsky_model(model_arg)
            message = f"✅ {result.message}" if result.success else f"❌ {result.message}"
            await self._safe_reply_with_fallback(update.message, message)

        await self._handle_command_errors(update, _execute)

    async def set_gigachat_model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_gigachat_model.

        Устанавливает модель GigaChat для генерации текстовых промптов.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args. Клиент GigaChat берётся из text_client.

        Side Effects:
            - Вызывает image_generator.text_client.set_model() для установки модели.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        if not await self._check_admin_access(update.effective_user.id, update.message):
            return

        if not self._has_args(context):
            await self._safe_reply_with_fallback(
                update.message,
                "📝 Использование: /set_gigachat_model <model_name>\n\n"
                "Используйте /list_models для просмотра доступных моделей.",
            )
            return

        model_name = context.args[0]

        async def _execute() -> None:
            result = await self._model_management_service.set_gigachat_model(model_name)
            await self._safe_reply_with_fallback(update.message, result.message)

        await self._handle_command_errors(update, _execute)

    async def list_models_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /list_models.

        Возвращает список всех доступных моделей Kandinsky и GigaChat.
        Текущая активная модель помечается звездочкой (⭐).
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Вызывает admin_dashboard_service.build_models_list_message() для получения списка моделей.
            - Отправляет форматированный список моделей пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /list_models от пользователя {user_id}")

        if not await self._check_admin_access(user_id, update.message):
            return

        async def _execute() -> None:
            message = await self._dashboard_service.build_models_list_message()
            await self._safe_reply_with_fallback(update.message, message)
            self.logger.info(f"Отправлен список моделей пользователю {user_id}")

        await self._handle_command_errors(update, _execute)
