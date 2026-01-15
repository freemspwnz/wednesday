from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BaseHandlers
from shared.base.exceptions import APIError, AuthenticationError, NetworkError
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger
from shared.retry import retry_on_connect_error


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

        try:
            result = await self._model_management_service.set_kandinsky_model(model_arg)
            if result.success:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ {result.message}",
                    max_retries=3,
                    delay=2,
                )
            else:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {result.message}",
                    max_retries=3,
                    delay=2,
                )
        except ValueError as e:
            self.logger.error(f"Ошибка при установке модели Kandinsky: {e}")
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {e!s}",
                    max_retries=3,
                    delay=2,
                )
            except Exception as send_error:
                # Обрабатываем ошибку отправки сообщения
                self._handle_send_message_error(
                    send_error,
                    context="отправке сообщения об ошибке установки модели Kandinsky",
                )
        except (AuthenticationError, NetworkError, APIError) as e:
            self.logger.error(f"Ошибка при установке модели Kandinsky: {e}")
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка API: {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception as api_error:
                # Обрабатываем ошибку отправки сообщения об ошибке API
                self._handle_send_message_error(
                    api_error,
                    context="отправке сообщения об ошибке API при установке модели Kandinsky",
                )
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при установке модели Kandinsky: {e}")

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

        try:
            result = await self._model_management_service.set_gigachat_model(model_name)
            await retry_on_connect_error(
                update.message.reply_text,
                result.message,
                max_retries=3,
                delay=2,
            )
        except ValueError as e:
            self.logger.error(f"Ошибка при установке модели GigaChat: {e}")
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {e!s}",
                    max_retries=3,
                    delay=2,
                )
            except Exception as send_error:
                # Обрабатываем ошибку отправки сообщения
                self._handle_send_message_error(
                    send_error,
                    context="отправке сообщения об ошибке установки модели GigaChat",
                )
        except (AuthenticationError, NetworkError, APIError) as e:
            self.logger.error(f"Ошибка при установке модели GigaChat: {e}")
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка API: {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception as api_error:
                # Обрабатываем ошибку отправки сообщения об ошибке API
                self._handle_send_message_error(
                    api_error,
                    context="отправке сообщения об ошибке API при установке модели GigaChat",
                )
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при установке модели GigaChat: {e}")

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

        try:
            message = await self._dashboard_service.build_models_list_message()
            await retry_on_connect_error(
                update.message.reply_text,
                message,
                max_retries=3,
                delay=2,
            )
            self.logger.info(f"Отправлен список моделей пользователю {user_id}")
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка моделей: {e}", exc_info=True)
            try:
                await retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка при получении списка моделей: {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception as send_error:
                # Обрабатываем ошибку отправки сообщения
                self._handle_send_message_error(
                    send_error,
                    context="отправке сообщения об ошибке установки модели Kandinsky",
                )
