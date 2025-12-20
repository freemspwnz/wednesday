from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.base_handlers import BaseHandlers
from services.bot_services import BotServices
from services.clients import get_image_client_container, get_text_client_container
from services.clients.exceptions import APIError, AuthenticationError, NetworkError

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
    ) -> None:
        super().__init__(services)
        # Клиенты используются для команд установки моделей,
        # а агрегированные списки моделей отдаёт AdminDashboardService.
        # Получаем клиенты напрямую из контейнеров.
        if self.services.admin_dashboard_service is None:
            raise ValueError("admin_dashboard_service must be provided in BotServices")
        self._dashboard_service = self.services.admin_dashboard_service
        # Получаем клиенты из контейнеров для установки моделей
        image_container = get_image_client_container()
        text_container = get_text_client_container()
        self.image_client = image_container
        self.text_client = text_container if text_container else None

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
            result = await self.image_client.set_model(model_arg)
            if result.success:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ {result.message}",
                    max_retries=3,
                    delay=2,
                )
            else:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {result.message}",
                    max_retries=3,
                    delay=2,
                )
        except ValueError as e:
            self.logger.error(f"Ошибка при установке модели Kandinsky: {e}")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {e!s}",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
        except (AuthenticationError, NetworkError, APIError) as e:
            self.logger.error(f"Ошибка при установке модели Kandinsky: {e}")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка API: {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
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
            result = await self.text_client.set_model(model_name)
            await self._retry_on_connect_error(
                update.message.reply_text,
                result.message,
                max_retries=3,
                delay=2,
            )
        except ValueError as e:
            self.logger.error(f"Ошибка при установке модели GigaChat: {e}")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ {e!s}",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
        except (AuthenticationError, NetworkError, APIError) as e:
            self.logger.error(f"Ошибка при установке модели GigaChat: {e}")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка API: {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
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
            message = await self._dashboard_service.build_models_list_message()
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
