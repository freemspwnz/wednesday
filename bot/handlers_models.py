from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.base_handlers import BaseHandlers
from services.bot_services import BotServices
from services.clients.factory import create_image_client, create_text_client

# Константы
TELEGRAM_SAFE_MESSAGE_LENGTH = 4000  # безопасная длина для обрезки сообщений


class ModelHandlers(BaseHandlers):
    """Обработчики команд управления моделями (Kandinsky и GigaChat).

    Инкапсулирует команды выбора и перечисления моделей генерации изображений
    и текстового клиента. Содержит полную реализацию всех модельных команд.
    """

    def __init__(
        self,
        services: BotServices,
        next_run_provider: Callable[[], datetime | None] | None = None,
    ) -> None:
        super().__init__(services)
        self.image_client = create_image_client()
        self.text_client = create_text_client()
        self.next_run_provider: Callable[[], datetime | None] | None = next_run_provider

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        if not await self.admins_store.is_admin(update.effective_user.id):
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Доступно только администратору",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ограничении доступа после {3} попыток: {e}")
            return

        if not context.args or len(context.args) == 0:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    (
                        "📝 Использование: /set_kandinsky_model <pipeline_id или название модели>\n\n"
                        "Используйте /list_models для просмотра доступных моделей.\n"
                        "Можно указать как ID (например: 12345678), так и название модели (например: kandinsky-2.2)"
                    ),
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return

        model_arg = " ".join(context.args)  # Объединяем аргументы на случай названий с пробелами
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                "⏳ Устанавливаю модель...",
                max_retries=3,
                delay=2,
            )
        except Exception as e:
            self.logger.error(f"Не удалось отправить сообщение о начале установки после {3} попыток: {e}")

        try:
            success, message = await self.image_client.set_model(model_arg)
            if success:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ {message}",
                    max_retries=3,
                    delay=2,
                )
            else:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {message}",
                    max_retries=3,
                    delay=2,
                )
        except Exception as e:
            self.logger.error(f"Ошибка при установке модели Kandinsky: {e}")

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        if not await self.admins_store.is_admin(update.effective_user.id):
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Доступно только администратору",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ограничении доступа после {3} попыток: {e}")
            return

        if not context.args or len(context.args) == 0:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📝 Использование: /set_gigachat_model <model_name>\n\n"
                    "Используйте /list_models для просмотра доступных моделей.",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return

        model_name = context.args[0]

        if not self.text_client:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ GigaChat клиент не инициализирован",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
            return

        try:
            _, message = await self.text_client.set_model(model_name)
            await self._retry_on_connect_error(
                update.message.reply_text,
                message,
                max_retries=3,
                delay=2,
            )
        except Exception as e:
            self.logger.error(f"Ошибка при установке модели GigaChat: {e}")

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
            - Вызывает image_generator.check_api_status() для получения моделей Kandinsky.
            - Вызывает image_generator.text_client.get_available_models() для получения моделей GigaChat.
            - Отправляет форматированный список моделей пользователю.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /list_models от пользователя {user_id}")

        if not await self.admins_store.is_admin(user_id):
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Доступно только администратору",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ограничении доступа после {3} попыток: {e}")
            return

        try:
            message_parts = ["📋 Доступные модели:\n"]

            # Получаем модели Kandinsky
            try:
                _api_ok, _api_status, api_models, current_kandinsky = await self.image_client.check_api_status()
                if api_models:
                    message_parts.append("🎨 Kandinsky (Kandinsky API):")
                    for model in api_models:
                        # Проверяем, является ли эта модель текущей
                        is_current = ""
                        if current_kandinsky[0]:
                            # Извлекаем ID из строки модели (формат: "Name (ID: 123)")
                            model_str = str(model)
                            if current_kandinsky[0] in model_str:
                                is_current = " ⭐"
                        message_parts.append(f"  • {model}{is_current}")
                else:
                    message_parts.append("🎨 Kandinsky: не удалось получить список моделей")
                    if current_kandinsky[0]:
                        message_parts.append(f"  Текущая: {current_kandinsky[1] or current_kandinsky[0]}")
            except Exception as e:
                self.logger.error(f"Ошибка при получении моделей Kandinsky: {e}")
                message_parts.append("🎨 Kandinsky: ошибка при получении списка моделей")
                from utils.models_store import ModelsStore

                models_store = ModelsStore()
                current_kandinsky_id, current_kandinsky_name = await models_store.get_kandinsky_model()
                if current_kandinsky_id:
                    message_parts.append(f"  Текущая: {current_kandinsky_name or current_kandinsky_id}")

            message_parts.append("")  # Пустая строка между секциями

            # Получаем модели GigaChat
            try:
                if self.text_client:
                    gigachat_models = await self.text_client.get_available_models()
                    from utils.models_store import ModelsStore

                    models_store = ModelsStore()
                    current_gigachat = await models_store.get_gigachat_model()

                    message_parts.append("🤖 GigaChat (GigaChat API):")
                    for model in gigachat_models:
                        is_current = " ⭐" if (current_gigachat and model == current_gigachat) else ""
                        message_parts.append(f"  • {model}{is_current}")
                else:
                    message_parts.append("🤖 GigaChat: не настроен (GIGACHAT_AUTHORIZATION_KEY не указан)")
            except Exception as e:
                self.logger.error(f"Ошибка при получении моделей GigaChat: {e}")
                message_parts.append("🤖 GigaChat: ошибка при получении списка моделей")
                from utils.models_store import ModelsStore

                models_store = ModelsStore()
                current_gigachat = await models_store.get_gigachat_model()
                if current_gigachat:
                    message_parts.append(f"  Текущая: {current_gigachat}")

            message = "\n".join(message_parts)

            # Проверяем длину сообщения (лимит Telegram: 4096 символов)
            if len(message) > TELEGRAM_SAFE_MESSAGE_LENGTH:
                truncated_parts = message_parts[: len(message_parts) // 2]
                message = "\n".join(truncated_parts) + "\n\n⚠️ Сообщение обрезано, часть моделей не показана"

            await self._retry_on_connect_error(
                update.message.reply_text,
                message,
                max_retries=3,
                delay=2,
            )
            self.logger.info(f"Отправлен список моделей пользователю {user_id}")
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка моделей: {e}", exc_info=True)
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка при получении списка моделей: {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
