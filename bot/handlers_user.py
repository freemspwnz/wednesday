from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from telegram import Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from bot.base_handlers import BaseHandlers
from services.bot_services import BotServices

# Константы
MAX_RETRIES_DEFAULT = 3  # количество попыток по умолчанию
RETRY_DELAY_DEFAULT = 2.0  # задержка между попытками по умолчанию


class UserHandlers(BaseHandlers):
    """Обработчики пользовательских команд бота.

    Этот класс инкапсулирует только пользовательские команды (/start, /help, /frog)
    и обработчик неизвестных команд. Содержит полную реализацию всех методов.
    """

    def __init__(
        self,
        services: BotServices,
        next_run_provider: Callable[[], datetime | None] | None = None,
    ) -> None:
        super().__init__(services)
        self.next_run_provider: Callable[[], datetime | None] | None = next_run_provider

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start.

        Приветствует пользователя и показывает основную информацию о боте,
        включая доступные команды и время следующей автоматической отправки
        (если доступно).

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Отправляет приветственное сообщение пользователю.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        self.logger.info(f"Получена команда /start от пользователя {update.effective_user.id}")

        next_run_info = ""
        if self.next_run_provider:
            try:
                next_dt = self.next_run_provider()
                if next_dt:
                    next_run_info = f"\n📅 Следующая отправка: {next_dt.strftime('%Y-%m-%d %H:%M')}"
            except Exception:
                pass

        welcome_message = (
            "🐸 Привет! Я Wednesday Frog Bot!\n\n"
            "Я генерирую изображения жабы по расписанию (каждую среду) и по команде.\n\n"
            "Доступные команды:\n"
            "/start - Показать это сообщение\n"
            "/help - Справка по командам\n"
            "/frog - Сгенерировать жабу прямо сейчас\n"
            f"{next_run_info}"
        )

        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                welcome_message,
                max_retries=3,
                delay=2,
            )
            self.logger.info("Отправлено приветственное сообщение")
        except Exception as e:
            self.logger.error(f"Не удалось отправить приветственное сообщение после {3} попыток: {e}")

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /help от пользователя {user_id}")

        # Проверка доступа администратора
        is_admin = await self.admins_store.is_admin(user_id)

        if is_admin:
            # Админская справка
            next_run_hint = ""
            if self.next_run_provider:
                try:
                    nxt = self.next_run_provider()
                    if nxt:
                        next_run_hint = f"\n   (Следующая отправка: {nxt.strftime('%Y-%m-%d %H:%M')})"
                except Exception:
                    pass

            help_message = (
                "🛠 Админ-справка по командам\n\n"
                "Пользовательские команды:\n"
                "• /start — приветствие и информация\n"
                "• /help — эта справка\n"
                "• /frog — сгенерировать жабу сейчас (rate limit, учитывается в лимитах)\n\n"
                "Админ-команды:\n"
                "• /status — расширенный статус: бот, планировщик, генерации, "
                "активные чаты, проверка API и метрики" + next_run_hint + "\n"
                "• /log [count] — отправить логи за N дней (1..10), без аргумента — последний файл\n"
                "• /add_chat <chat_id> — добавить чат в рассылку\n"
                "• /remove_chat <chat_id> — удалить чат из рассылки\n"
                "• /list_chats — список активных чатов с ID\n"
                "• /force_send — принудительная отправка в подключенные чаты\n"
                "• /set_kandinsky_model <pipeline_id> — установить модель Kandinsky\n"
                "• /set_gigachat_model <model_name> — установить модель GigaChat\n"
                "• /mod <user_id> или ответ на сообщение — предоставить админ-права "
                "пользователю (только главный админ)\n"
                "• /unmod <user_id> или ответ на сообщение — удалить админ-права у "
                "пользователя (только главный админ)\n"
                "• /unmod без аргументов — показать список всех админов "
                "(только главный админ)\n"
                "• /list_mods — список всех админов с ID\n"
                "• /set_frog_limit <threshold> — порог ручных /frog (1..100, не выше квоты)\n"
                "• /set_frog_used <count> — установить текущее число ручных /frog за месяц\n"
                "• /help — эта справка"
            )
            self.logger.info("Отправлена админская справка")
        else:
            # Пользовательская справка
            # Получаем информацию о следующей отправке
            scheduler_info = ""
            if self.next_run_provider:
                try:
                    next_dt = self.next_run_provider()
                    if next_dt:
                        # Определяем день недели на русском
                        weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
                        weekday = weekdays[next_dt.weekday()]
                        next_dt_str = next_dt.strftime("%Y-%m-%d %H:%M")
                        scheduler_info = f"\n• Ближайшая автоматическая отправка: {next_dt_str} ({weekday})"
                except Exception:
                    pass

            help_message = (
                "📚 Справка по командам Wednesday Frog Bot\n\n"
                "🔹 /start - Приветствие и основная информация\n"
                "🔹 /help - Эта справка\n"
                "🔹 /frog - Сгенерировать изображение жабы прямо сейчас\n\n"
                "ℹ️ Информация:\n"
                f"• Автоматическая отправка каждый раз по расписанию{scheduler_info}\n"
                "• Изображения генерируются с помощью нейросети Kandinsky\n\n"
                "🐛 Если что-то не работает, обратитесь к администратору."
            )
            self.logger.info("Отправлена пользовательская справка")

        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                help_message,
                max_retries=3,
                delay=2,
            )
        except Exception as e:
            self.logger.error(f"Не удалось отправить справку после {3} попыток: {e}")

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
            - Ставит Celery-задачу через FrogRequestService.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        chat_id = update.message.chat_id
        self.logger.info(f"Получена команда /frog от пользователя {user_id}")

        # Проверка на админа
        is_admin = await self.admins_store.is_admin(user_id)

        # Проверка rate limit через application service
        is_allowed, rate_limit_message = await self.services.frog_rate_limiter.check_and_consume(
            user_id=user_id,
            is_admin=is_admin,
        )
        if not is_allowed:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    rate_limit_message or "⏰ Повторная генерация временно недоступна",
                    max_retries=MAX_RETRIES_DEFAULT,
                    delay=RETRY_DELAY_DEFAULT,
                )
            except (TelegramError, NetworkError, TimedOut) as e:
                self.logger.error(
                    f"Не удалось отправить сообщение о rate limit после {MAX_RETRIES_DEFAULT} попыток: {e}",
                )
            return

        # Проверяем лимит генераций
        usage = self.services.usage
        if usage and not await usage.can_use_frog():
            total, threshold, quota = await usage.get_limits_info()
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    (
                        "🚫 Лимит ручных генераций на этот месяц исчерпан.\n"
                        f"Использовано: {total}/{quota}. Доступ к /frog закрыт после {threshold}.\n"
                        "Ожидайте автоматических отправок по средам."
                    ),
                    max_retries=MAX_RETRIES_DEFAULT,
                    delay=RETRY_DELAY_DEFAULT,
                )
            except (TelegramError, NetworkError, TimedOut) as e:
                self.logger.error(
                    f"Не удалось отправить сообщение о лимите после {MAX_RETRIES_DEFAULT} попыток: {e}",
                )
            return

        # Отправляем сообщение о начале генерации
        status_message = None
        try:
            status_message = await self._retry_on_connect_error(
                update.message.reply_text,
                "🐸 Генерирую жабу для вас... Это может занять несколько секунд.",
                max_retries=MAX_RETRIES_DEFAULT,
                delay=RETRY_DELAY_DEFAULT,
            )
        except Exception as e:
            self.logger.error(
                f"Не удалось отправить сообщение о начале генерации после {MAX_RETRIES_DEFAULT} попыток: {e}",
            )
            # Продолжаем даже если не удалось отправить статус

        # Ставим задачу в очередь Celery через application service
        try:
            await self.services.frog_request_service.request_manual_frog(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message.message_id if status_message else None,
            )
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу в очередь Celery: {e}")
            # Удаляем статусное сообщение
            if status_message:
                try:
                    await status_message.delete()
                except Exception:
                    pass
            # Отправляем сообщение пользователю об ошибке
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "⚠️ Не удалось поставить запрос в очередь. Попробуйте позже.",
                    max_retries=3,
                    delay=2,
                )
            except Exception as send_error:
                self.logger.error(f"Не удалось отправить сообщение об ошибке очереди: {send_error}")

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
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

        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                unknown_message,
                max_retries=3,
                delay=2,
            )
            self.logger.info("Отправлено сообщение о неизвестной команде")
        except Exception as e:
            self.logger.error(f"Не удалось отправить сообщение о неизвестной команде после {3} попыток: {e}")
