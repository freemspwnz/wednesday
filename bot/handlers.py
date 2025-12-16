"""
Обработчики команд для Telegram бота.
Содержит функции для обработки различных команд пользователей.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TypeVar

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from services.celery_app import celery_app
from services.image_generator import ImageGenerator
from utils.admins_store import AdminsStore
from utils.config import config
from utils.logger import get_logger, log_all_methods

# Константы
FROG_RATE_LIMIT_MINUTES = 5  # минимальный интервал в минутах
FROG_RATE_LIMIT_WINDOW_SECONDS = 60  # окно в секундах
FROG_RATE_LIMIT_MAX_REQUESTS = 10  # максимум запросов в окне
MAX_FROG_THRESHOLD = 100  # максимальный порог ручных генераций
SECONDS_PER_MINUTE = 60  # секунд в минуте
MAX_RETRIES_DEFAULT = 3  # количество попыток по умолчанию
RETRY_DELAY_DEFAULT = 2.0  # задержка между попытками по умолчанию
MAX_ERROR_DETAILS_LENGTH = 500  # максимальная длина деталей ошибки
MAX_TRACE_LENGTH = 1500  # максимальная длина трейса
MAX_MESSAGE_LENGTH = 4000  # максимальная длина сообщения Telegram
PERCENT_MULTIPLIER = 100  # множитель для процентов
MAX_LOG_DAYS = 10  # максимальное количество дней для команды /log
TELEGRAM_MAX_MESSAGE_LENGTH = 4096  # максимальная длина сообщения Telegram API
TELEGRAM_SAFE_MESSAGE_LENGTH = 4000  # безопасная длина для обрезки сообщений

T = TypeVar("T")


@log_all_methods()
class CommandHandlers:
    """Класс для обработки команд Telegram бота.

    Обеспечивает обработку всех команд пользователей и администраторов:

    Пользовательские команды:
    - /start - приветствие и основная информация
    - /help - справка по командам (разная для админов и пользователей)
    - /frog - ручная генерация изображения жабы с rate limiting

    Административные команды:
    - /status - расширенный статус бота и систем
    - /log - отправка логов администратору
    - /force_send - принудительная отправка изображения в чат(ы)
    - /add_chat, /remove_chat, /list_chats - управление списком рассылки
    - /mod, /unmod, /list_mods - управление администраторами
    - /set_frog_limit, /set_frog_used - управление лимитами генераций
    - /set_kandinsky_model, /set_gigachat_model, /list_models - управление моделями
    - /stop - остановка бота

    Все команды включают обработку ошибок, rate limiting (где применимо) и
    логирование операций.
    """

    def __init__(
        self,
        image_generator: ImageGenerator,
        next_run_provider: Callable[[], datetime | None] | None = None,
    ) -> None:
        """Инициализирует обработчики команд.

        Создает экземпляр CommandHandlers с необходимыми зависимостями
        и настраивает rate limiting для команды /frog.

        Args:
            image_generator: Экземпляр генератора изображений, используемый
                для генерации изображений жабы по команде /frog.
            next_run_provider: Опциональная функция для получения времени
                следующего запуска автоматической отправки. Используется для
                отображения информации о следующей отправке в командах /start и /help.
                Если None, информация о следующей отправке не отображается.
        """
        self.logger = get_logger(__name__)
        self.logger.info("Начало инициализации CommandHandlers")
        self.image_generator: ImageGenerator = image_generator
        self.next_run_provider: Callable[[], datetime | None] | None = next_run_provider
        # Инициализируем хранилище админов
        self.logger.info("Инициализация хранилища админов")
        self.admins_store: AdminsStore = AdminsStore()

        # Rate limiting для /frog
        self._frog_rate_limit: dict[int, float] = {}  # {user_id: last_call_timestamp}
        self._frog_rate_limit_minutes: int = FROG_RATE_LIMIT_MINUTES
        self._global_frog_rate_limit: dict[float, int] = {}  # {timestamp: count}
        self._global_frog_rate_limit_window: int = FROG_RATE_LIMIT_WINDOW_SECONDS
        self._global_frog_rate_limit_max: int = FROG_RATE_LIMIT_MAX_REQUESTS

        self.logger.info("CommandHandlers успешно инициализирован")

    async def set_frog_limit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_frog_limit.

        Устанавливает порог ручных генераций /frog (максимум 100).
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к данным приложения через context.application.bot_data.

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
            await update.message.reply_text("❌ Доступно только администратору")
            return
        if not context.args or len(context.args) < 1:
            self.logger.warning("set_frog_limit_command: аргументы не предоставлены")
            await update.message.reply_text(
                f"📝 Использование: /set_frog_limit <threshold> (1..{MAX_FROG_THRESHOLD})",
            )
            return
        try:
            raw = int(context.args[0])
            self.logger.info(f"set_frog_limit_command: запрошенный порог: {raw}")
            if raw <= 0:
                raise ValueError(f"Порог должен быть положительным числом, получено: {raw}")
            # Ограничим максимумом MAX_FROG_THRESHOLD
            desired = min(raw, MAX_FROG_THRESHOLD)
            usage = context.application.bot_data.get("usage")
            if usage:
                new_threshold = await usage.set_frog_threshold(desired)
                total, _threshold, quota = await usage.get_limits_info()
                self.logger.info(
                    f"set_frog_limit_command: порог установлен на {new_threshold}, использование: {total}/{quota}",
                )
                await update.message.reply_text(
                    f"✅ Порог /frog установлен: {new_threshold} (текущее использование: {total}/{quota})",
                )
                self.logger.info("set_frog_limit_command: команда выполнена успешно")
            else:
                self.logger.error("set_frog_limit_command: хранилище использования не инициализировано")
                await update.message.reply_text("❌ Хранилище использования не инициализировано")
        except ValueError as e:
            self.logger.error(f"set_frog_limit_command: ошибка валидации параметра: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Неверный параметр. Использование: /set_frog_limit <threshold> (1..{MAX_FROG_THRESHOLD})",
            )
        except Exception as e:
            self.logger.error(f"set_frog_limit_command: неожиданная ошибка: {e}", exc_info=True)
            raise

    async def set_frog_used_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_frog_used.

        Устанавливает текущее значение выработки /frog за месяц.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к данным приложения через context.application.bot_data.

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
            await update.message.reply_text("❌ Доступно только администратору")
            return
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("📝 Использование: /set_frog_used <count>")
            return
        try:
            raw = int(context.args[0])
            if raw < 0:
                raise ValueError
            usage = context.application.bot_data.get("usage")
            if usage:
                # Ограничим значением квоты
                capped = min(raw, usage.monthly_quota)
                await usage.set_month_total(capped)
                total, threshold, quota = await usage.get_limits_info()
                await update.message.reply_text(
                    f"✅ Текущее использование /frog: {total}/{threshold} (квота: {quota})",
                )
            else:
                await update.message.reply_text("❌ Хранилище использования не инициализировано")
        except ValueError:
            await update.message.reply_text("❌ Неверный параметр. Использование: /set_frog_used <count>")

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = update.effective_user.id
        if not await self.admins_store.is_admin(user_id):
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Доступно только администратору",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
            return

        from pathlib import Path

        from utils.paths import LOGS_CONTAINER_PATH, LOGS_DIR

        logs_dir = Path(LOGS_DIR)
        if not logs_dir.exists():
            try:
                self.logger.info(
                    f"Запрошена команда /log, но директория логов отсутствует: {logs_dir} "
                    f"(контейнерный путь: {LOGS_CONTAINER_PATH})",
                )
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Папка logs пуста или отсутствует",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
            return

        # Парсим аргумент count
        count = 1
        capped_note = None
        if context.args and len(context.args) > 0:
            raw = context.args[0]
            if not raw.isdigit():
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Неверный аргумент. Используйте: /log [count], где count — число 1..10",
                        max_retries=3,
                        delay=2,
                    )
                except Exception:
                    pass
                return
            count = int(raw)
            if count > MAX_LOG_DAYS:
                count = MAX_LOG_DAYS
                capped_note = f"(ограничено максимумом {MAX_LOG_DAYS} дней)"

        # Определяем файлы по датам за count дней, учитывая .log и .log.zip
        from datetime import datetime, timedelta
        from pathlib import Path as PathLib

        wanted_dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(count)]
        candidates: list[PathLib] = []
        for ds in wanted_dates:
            log_path = logs_dir / f"wednesday_bot_{ds}.log"
            zip_path = logs_dir / f"wednesday_bot_{ds}.log.zip"
            if log_path.exists():
                candidates.append(log_path)
            elif zip_path.exists():
                candidates.append(zip_path)

        # Фоллбек: если ничего не нашли по датам — возьмем самый свежий файл
        if not candidates:
            log_files = [p for p in logs_dir.iterdir() if p.is_file()]
            candidates = sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)[:1]

        if not candidates:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Нет логов для отправки",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass
            return

        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                f"📦 Отправляю файл(ы) логов за {len(candidates)} дн. {capped_note or ''}",
                max_retries=3,
                delay=2,
            )
        except Exception:
            pass

        # Отправляем в порядке от старых к новым
        for lf in sorted(candidates, key=lambda p: p.name):
            try:
                self.logger.info(
                    f"Отправляю лог-файл {lf} (контейнерный путь: {LOGS_CONTAINER_PATH}/{lf.name})",
                )
                with lf.open("rb") as fh:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=fh, filename=lf.name)
            except Exception as e:
                self.logger.warning(
                    f"Ошибка при отправке лога {lf} (контейнерный путь: {LOGS_CONTAINER_PATH}/{lf.name}): {e}",
                )
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                "✅ Готово",
                max_retries=3,
                delay=2,
            )
        except Exception:
            pass

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /stop.

        Останавливает бота полностью. Команда доступна только администраторам.
        После выполнения команды основной бот останавливается и запускается
        SupportBot для обслуживания резервных функций.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к экземпляру бота
                через context.application.bot_data.get("bot") для остановки.

        Side Effects:
            - Сохраняет метаданные сообщения для последующего редактирования.
            - Вызывает bot.stop() для остановки основного бота.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /stop от пользователя {user_id}")

        # Проверка прав администратора
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

        # В админ-чате НЕ отправляем короткое статусное сообщение (только полные сообщения об остановке)
        is_admin_chat = False
        try:
            from utils.config import config as _cfg

            admin_chat_id_env = getattr(_cfg, "admin_chat_id", None)
            if admin_chat_id_env and update.effective_chat and update.effective_chat.id is not None:
                try:
                    is_admin_chat = int(str(admin_chat_id_env)) == int(str(update.effective_chat.id))
                except Exception:
                    is_admin_chat = False
        except Exception:
            is_admin_chat = False

        # Отправляем статус только если это НЕ админ-чат
        status_msg = None
        if not is_admin_chat:
            try:
                status_msg = await self._retry_on_connect_error(
                    update.message.reply_text,
                    "🛑 Останавливаю Wednesday Frog Bot...",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                status_msg = None

        # Сохраняем метаданные сообщения в экземпляр основного бота (только для не-админ чатов)
        try:
            bot_instance = context.application.bot_data.get("bot")
            if (not is_admin_chat) and bot_instance is not None and status_msg is not None and update.effective_chat:
                bot_instance.pending_shutdown_edit = {
                    "chat_id": update.effective_chat.id,
                    "message_id": getattr(status_msg, "message_id", None),
                }
        except Exception:
            pass

        # Получаем экземпляр основного бота из bot_data и останавливаем его
        try:
            bot_instance = context.application.bot_data.get("bot")
            if bot_instance is not None:
                await bot_instance.stop()
            else:
                # Фоллбек: попытаться аккуратно остановить приложение
                try:
                    if hasattr(context.application, "updater") and context.application.updater:
                        await context.application.updater.stop()
                except Exception:
                    pass
                try:
                    await context.application.stop()
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Ошибка при попытке остановить бота через /stop: {e}")

    async def _retry_on_connect_error(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        max_retries: int = MAX_RETRIES_DEFAULT,
        delay: float = RETRY_DELAY_DEFAULT,
        **kwargs: object,
    ) -> T:
        """
        Выполняет функцию с повторными попытками при ошибках httpx.ConnectError.

        Args:
            func: Асинхронная функция для выполнения
            *args: Позиционные аргументы для функции
            max_retries: Максимальное количество попыток (по умолчанию 3)
            delay: Задержка между попытками в секундах (по умолчанию 2)
            **kwargs: Именованные аргументы для функции

        Returns:
            Результат выполнения функции

        Raises:
            Последняя ошибка, если все попытки исчерпаны
        """
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = delay * attempt  # Экспоненциальная задержка
                    self.logger.warning(
                        f"Ошибка подключения (попытка {attempt}/{max_retries}): {e}. Повтор через {wait_time}с...",
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"Все {max_retries} попытки исчерпаны. Последняя ошибка: {e}")
            except Exception:
                # Для других ошибок не делаем повторных попыток
                raise

        # Если дошли сюда, все попытки исчерпаны
        if last_error is not None:
            raise last_error
        # Если last_error None (не должно случиться, но для безопасности)
        raise RuntimeError("Все попытки исчерпаны, но ошибка не была сохранена")

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
                "• /mod <user_id> — предоставить админ-права пользователю\n"
                "• /unmod <user_id> — удалить админ-права у пользователя\n"
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
            context: Контекст бота, предоставляющий доступ к хранилищу использования
                через context.application.bot_data.get("usage") для проверки лимитов.

        Side Effects:
            - Проверяет глобальный и per-user rate limits.
            - Проверяет месячный лимит генераций через usage.can_use_frog().
            - Отправляет статусное сообщение пользователю.
            - Ставит Celery-задачу wednesday.send_frog_manual в очередь.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        chat_id = update.message.chat_id
        self.logger.info(f"Получена команда /frog от пользователя {user_id}")

        # Rate limit: глобальный
        import time

        now = time.time()
        self._global_frog_rate_limit = {
            ts: cnt
            for ts, cnt in self._global_frog_rate_limit.items()
            if now - ts < self._global_frog_rate_limit_window
        }
        recent_count = sum(self._global_frog_rate_limit.values())
        if recent_count >= self._global_frog_rate_limit_max:
            self.logger.warning(f"Глобальный rate limit /frog: {recent_count}/{self._global_frog_rate_limit_max}")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "🚦 Слишком много запросов! Попробуйте через минуту.",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение о rate limit после {3} попыток: {e}")
            return

        # Проверка на админа - пропускаем per-user rate limit для админа
        is_admin = await self.admins_store.is_admin(user_id)

        # Rate limit: per-user (пропускаем для админа)
        if not is_admin:
            last_call = self._frog_rate_limit.get(user_id, 0)
            if now - last_call < self._frog_rate_limit_minutes * SECONDS_PER_MINUTE:
                remaining = int(
                    self._frog_rate_limit_minutes * SECONDS_PER_MINUTE - (now - last_call),
                )
                self.logger.info(f"Rate limit для пользователя {user_id}: {remaining}с осталось")
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        f"⏰ Повторная генерация доступна через {remaining}с",
                        max_retries=MAX_RETRIES_DEFAULT,
                        delay=RETRY_DELAY_DEFAULT,
                    )
                except Exception as e:
                    self.logger.error(
                        f"Не удалось отправить сообщение о rate limit после {MAX_RETRIES_DEFAULT} попыток: {e}",
                    )
                return

            self._frog_rate_limit[user_id] = now

        self._global_frog_rate_limit[now] = self._global_frog_rate_limit.get(now, 0) + 1

        # Проверяем лимит генераций (храним в application.bot_data)
        usage = context.application.bot_data.get("usage")
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
            except Exception as e:
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

        # Ставим задачу в очередь Celery
        try:
            celery_app.send_task(
                "wednesday.send_frog_manual",
                args=[chat_id, user_id, status_message.message_id if status_message else None],
            )
            self.logger.info(f"Задача send_frog_manual поставлена в очередь для пользователя {user_id}")
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

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /status.

        Показывает расширенный статус бота, включая информацию о статусе бота,
        планировщике, лимитах генераций, активных чатах, проверку API (Kandinsky и GigaChat)
        и метрики производительности. Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к хранилищам через
                context.application.bot_data (usage, chats, metrics) и к боту
                через context.bot для получения информации о боте.

        Side Effects:
            - Вызывает image_generator.check_api_status() для проверки Kandinsky API.
            - Вызывает image_generator.text_client.check_api_status() для проверки GigaChat API.
            - Получает информацию о лимитах через usage.get_limits_info().
            - Получает список чатов через chats.list_chat_ids().
            - Получает метрики через metrics.get_summary().
            - Отправляет подробный статус пользователю.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /status от пользователя {user_id}")

        # Проверка доступа администратора
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
            # Получаем информацию о статусе бота
            bot_info = await context.bot.get_me()

            # Информация о следующей отправке
            next_run_line = ""
            scheduler_status = "❌ Не настроен"
            if self.next_run_provider:
                try:
                    next_dt = self.next_run_provider()
                    if next_dt:
                        next_run_line = f"📅 Следующая отправка: {next_dt.strftime('%Y-%m-%d %H:%M')}\n"
                        scheduler_status = f"✅ Следующая отправка: {next_dt.strftime('%Y-%m-%d %H:%M')}"
                except Exception:
                    pass

            # Проверяем API без генерации (dry-run)
            api_status: str = "⏳ Проверка..."
            _api_models: list[str] = []
            current_kandinsky: tuple[str | None, str | None] = (None, None)
            api_ok: bool = False
            try:
                api_ok, api_status, _api_models, current_kandinsky = await self.image_generator.check_api_status()
                if not api_ok:
                    self.logger.warning(f"Проверка API Kandinsky не прошла: {api_status}")
            except Exception as e:
                api_ok = False
                api_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
                self.logger.error(f"Ошибка при проверке API: {e}", exc_info=True)

            # Проверяем GigaChat API без траты токенов
            gigachat_status: str = "N/A"
            current_gigachat: str | None = None
            if self.image_generator.text_client:
                try:
                    gigachat_ok: bool
                    gigachat_ok, gigachat_status = await self.image_generator.text_client.check_api_status()
                    if not gigachat_ok:
                        self.logger.warning(f"Проверка API GigaChat не прошла: {gigachat_status}")
                    # Получаем доступные модели GigaChat
                    _gigachat_models = await self.image_generator.text_client.get_available_models()
                    from utils.models_store import ModelsStore

                    models_store = ModelsStore()
                    current_gigachat = await models_store.get_gigachat_model() or "GigaChat"
                except Exception as e:
                    gigachat_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
                    self.logger.error(f"Ошибка при проверке GigaChat API: {e}", exc_info=True)
            else:
                gigachat_status = "⚠️  Не настроен (GIGACHAT_AUTHORIZATION_KEY не указан)"

            # Информация об использовании и лимитах
            usage = context.application.bot_data.get("usage")
            usage_info = "N/A"
            if usage:
                total, threshold, quota = await usage.get_limits_info()
                used_percent = int(total / quota * PERCENT_MULTIPLIER) if quota else 0
                usage_info = f"{total}/{quota} ({used_percent}%), порог: {threshold}"

            # Информация об активных чатах
            chats = context.application.bot_data.get("chats")
            chats_info: str | int = "N/A"
            if chats:
                chats_info = len(await chats.list_chat_ids())

            # Метрики производительности (из /health)
            metrics = context.application.bot_data.get("metrics")
            metrics_text = "Не настроены"
            if metrics:
                m_sum = await metrics.get_summary()
                total_requests = m_sum["generations_total"]
                successful = m_sum["generations_success"]
                success_rate = (successful / total_requests * PERCENT_MULTIPLIER) if total_requests > 0 else 0
                metrics_text = (
                    f"• Всего запросов на генерацию: {total_requests}\n"
                    f"• Успешных генераций: {successful}\n"
                    f"• Процент успеха: {success_rate:.1f}%\n"
                    f"• Среднее время генерации: {m_sum['average_generation_time']}\n"
                    f"• Срабатываний circuit breaker: {m_sum['circuit_breaker_trips']}"
                )

            # Форматируем информацию о текущих моделях (только активные, не все доступные)
            kandinsky_current_text = ""
            if current_kandinsky[0]:
                kandinsky_current_text = f"  ⭐ Текущая модель: {current_kandinsky[1] or current_kandinsky[0]}"
            else:
                kandinsky_current_text = "  ⚠️ Модель не выбрана"

            # Форматируем информацию о текущей модели GigaChat
            gigachat_current_text = ""
            if current_gigachat:
                gigachat_current_text = f"  ⭐ Текущая модель: {current_gigachat}"
            else:
                gigachat_current_text = "  ⚠️ Модель не выбрана"

            status_message = (
                f"🤖 Статус бота: {bot_info.first_name}\n\n"
                "✅ Бот активен и работает\n"
                f"{next_run_line}"
                "🎨 Генератор изображений: Kandinsky API\n"
                "📝 Логирование: включено\n\n"
                "🔌 Проверка систем:\n"
                f"• API Kandinsky: {api_status}\n"
                f"{kandinsky_current_text}\n"
                f"• API GigaChat: {gigachat_status}\n"
                f"{gigachat_current_text}\n"
                f"• Планировщик: {scheduler_status}\n\n"
                "📊 Статистика:\n"
                f"• Генерации: {usage_info}\n"
                f"• Активных чатов: {chats_info}\n\n"
                "📈 Метрики производительности:\n"
                f"{metrics_text}\n\n"
                "💡 Используйте /list_models для просмотра всех доступных моделей\n\n"
                "🔄 Последняя проверка: прямо сейчас\n"
                "💚 Все системы работают нормально!"
            )

            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    status_message,
                    max_retries=3,
                    delay=2,
                )
                self.logger.info("Отправлен статус бота")
            except Exception as e:
                self.logger.error(f"Не удалось отправить статус после {3} попыток: {e}")
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        f"❌ Ошибка при получении статуса: {str(e)[:200]}",
                        max_retries=3,
                        delay=2,
                    )
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Ошибка при получении статуса: {e}")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка при получении статуса: {str(e)[:200]}",
                    max_retries=3,
                    delay=2,
                )
            except Exception:
                pass

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

    async def admin_force_send_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /force_send.

        Выполняет принудительную отправку изображения жабы в указанный чат(ы)
        или во все активные чаты. Команда доступна только администраторам.
        Без аргументов показывает список активных чатов.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args, к хранилищу чатов через context.application.bot_data.get("chats"),
                и к боту для отправки сообщений через context.bot.

        Side Effects:
            - Вызывает image_generator.generate_frog_image() для генерации нового изображения
              (если лимит не исчерпан).
            - Использует image_generator.get_random_saved_image() как fallback при недоступности генерации.
            - Отправляет изображение в указанные чаты через context.bot.send_photo().
            - Вызывает usage.increment() для увеличения счетчика использования.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /force_send от пользователя {user_id}")

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

        chats = context.application.bot_data.get("chats")
        if not chats:
            self.logger.warning("Хранилище чатов не настроено")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Хранилище чатов не настроено",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
            return

        chat_ids = await chats.list_chat_ids()
        if not chat_ids:
            self.logger.info("Нет активных чатов")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Нет активных чатов для отправки",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}")
            return

        # Если аргумент не передан - показываем список чатов
        if not context.args or len(context.args) == 0:
            # Получаем информацию о чатах
            chat_list = []
            for chat_id in chat_ids:
                try:
                    chat_info = await context.bot.get_chat(chat_id)
                    title = getattr(chat_info, "title", getattr(chat_info, "first_name", "Unknown"))
                    chat_list.append(f"• {title} (ID: {chat_id})")
                except Exception as e:
                    self.logger.warning(f"Не удалось получить информацию о чате {chat_id}: {e}")
                    chat_list.append(f"• Чат {chat_id} (не удалось получить информацию)")

            message = (
                "📋 Активные чаты для отправки:\n\n"
                + "\n".join(chat_list)
                + "\n\n"
                + "💡 Использование:\n"
                + "• /force_send <chat_id> — отправить жабу в указанный чат\n"
                + "• /force_send all — отправить жабу во все чаты"
            )
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    message,
                    max_retries=3,
                    delay=2,
                )
                self.logger.info(f"Отправлен список из {len(chat_ids)} активных чатов пользователю {user_id}")
            except Exception as e:
                self.logger.error(f"Не удалось отправить список чатов после {3} попыток: {e}")
            return

        # Получаем аргумент
        arg = context.args[0].strip().lower()

        # Проверяем лимит генераций
        usage = context.application.bot_data.get("usage")
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
                    try:
                        await self._retry_on_connect_error(
                            update.message.reply_text,
                            f"❌ Чат {requested_chat_id} не найден в списке активных чатов",
                            max_retries=3,
                            delay=2,
                        )
                    except Exception as e:
                        self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
                    return
            except ValueError:
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Неверный аргумент. Используйте: /force_send <chat_id> или /force_send all",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
                return

        if not target_chat_ids:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Нет целевых чатов для отправки",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
            return

        # Отправляем статусное сообщение
        try:
            status_msg = await self._retry_on_connect_error(
                update.message.reply_text,
                f"🔄 Генерирую и отправляю жабу в {len(target_chat_ids)} чат(ов)...",
                max_retries=3,
                delay=2,
            )
        except Exception as e:
            self.logger.error(f"Не удалось отправить статусное сообщение после {3} попыток: {e}")
            status_msg = None

        # Генерируем или получаем изображение
        image_data: bytes | None = None
        caption: str = ""
        use_fallback = False

        if can_generate:
            try:
                result = await self.image_generator.generate_frog_image(user_id=user_id)
                if result:
                    image_data, caption = result
                    # Сохраняем изображение локально
                    try:
                        saved_path = self.image_generator.save_image_locally(image_data, prefix="frog")
                        if saved_path:
                            self.logger.info(
                                f"Изображение сохранено локально и доступно в контейнере по пути {saved_path}",
                            )
                    except Exception:
                        # Ошибка локального сохранения не должна ломать рассылку.
                        pass
                    # Увеличиваем счетчик использования
                    if usage:
                        await usage.increment(1)
                else:
                    use_fallback = True
                    self.logger.warning("Генерация изображения вернула None, используем fallback")
            except Exception as e:
                self.logger.error(f"Ошибка при генерации изображения: {e}", exc_info=True)
                use_fallback = True
        else:
            use_fallback = True
            self.logger.info("Лимит генераций исчерпан, используем fallback")

        # Если нужно использовать fallback
        if use_fallback:
            fallback_image = self.image_generator.get_random_saved_image()
            if fallback_image:
                image_data, caption = fallback_image
                self.logger.info("Используется случайное изображение из архива")
            else:
                self.logger.warning("Нет сохраненных изображений для отправки")
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Не удалось получить изображение (лимит исчерпан и нет сохраненных изображений)",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
                if status_msg:
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                return

        if not image_data:
            self.logger.error("Не удалось получить изображение для отправки")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Не удалось получить изображение для отправки",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            return

        # Отправляем изображение главному админу
        admin_chat_id = config.admin_chat_id
        if admin_chat_id:
            try:
                admin_id = int(admin_chat_id)
                await self._retry_on_connect_error(
                    context.bot.send_photo,
                    chat_id=admin_id,
                    photo=image_data,
                    caption=f"🐸 Принудительная отправка (команда /force_send)\n\n{caption}",
                    max_retries=3,
                    delay=2,
                )
                self.logger.info(f"Изображение отправлено главному админу {admin_id}")
            except (ValueError, TypeError) as e:
                self.logger.warning(f"Неверный формат admin_chat_id: {e}")
            except Exception as e:
                self.logger.warning(f"Не удалось отправить изображение главному админу: {e}")

        # Отправляем изображение в целевые чаты
        success_count = 0
        failed_count = 0
        for target_chat_id in target_chat_ids:
            try:
                await self._retry_on_connect_error(
                    context.bot.send_photo,
                    chat_id=target_chat_id,
                    photo=image_data,
                    caption=caption,
                    max_retries=3,
                    delay=2,
                )
                success_count += 1
                self.logger.info(f"Изображение отправлено в чат {target_chat_id}")
            except Exception as e:
                failed_count += 1
                self.logger.warning(f"Не удалось отправить изображение в чат {target_chat_id}: {e}")

        # Удаляем статусное сообщение и отправляем итоговое
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

        result_message = (
            f"✅ Отправка выполнена:\n"
            f"• Успешно: {success_count}/{len(target_chat_ids)}\n"
            f"• Ошибок: {failed_count}\n"
            f"• Использован: {'fallback (лимит исчерпан)' if use_fallback else 'новая генерация'}"
        )
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                result_message,
                max_retries=3,
                delay=2,
            )
            self.logger.info(f"Команда /force_send выполнена: {success_count} успешных отправок")
        except Exception as e:
            self.logger.error(f"Не удалось отправить итоговое сообщение после {3} попыток: {e}")

    async def admin_add_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /add_chat.

        Добавляет чат в список рассылки для автоматических отправок.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к хранилищу чатов через context.application.bot_data.get("chats").

        Side Effects:
            - Вызывает chats.add_chat() для добавления чата в хранилище.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.

        Raises:
            ValueError: Если переданный chat_id не является числом.
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
                    "📝 Использование: /add_chat <chat_id>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return

        try:
            chat_id = int(context.args[0])
            chats = context.application.bot_data.get("chats")
            if chats:
                await chats.add_chat(chat_id, "Manually added")
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        f"✅ Чат {chat_id} добавлен в рассылку",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об успехе после {3} попыток: {e}")
        except ValueError:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Неверный chat_id (должен быть числом)",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")

    async def admin_remove_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /remove_chat.

        Удаляет чат из списка рассылки для автоматических отправок.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к хранилищу чатов через context.application.bot_data.get("chats").

        Side Effects:
            - Вызывает chats.remove_chat() для удаления чата из хранилища.
            - Отправляет ответное сообщение пользователю с результатом операции.

        Raises:
            ValueError: Если переданный chat_id не является числом.
        """
        if not update.message or not update.effective_user:
            return

        if not await self.admins_store.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступно только администратору")
            return

        if not context.args or len(context.args) == 0:
            await update.message.reply_text("📝 Использование: /remove_chat <chat_id>")
            return

        try:
            chat_id = int(context.args[0])
            chats = context.application.bot_data.get("chats")
            if chats:
                await chats.remove_chat(chat_id)
                await update.message.reply_text(f"✅ Чат {chat_id} удалён из рассылки")
        except ValueError:
            await update.message.reply_text("❌ Неверный chat_id (должен быть числом)")

    async def list_chats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /list_chats.

        Возвращает список всех активных чатов с их ID и названиями.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к хранилищу чатов
                через context.application.bot_data.get("chats") и к боту
                для получения информации о чатах через context.bot.get_chat().

        Side Effects:
            - Вызывает chats.list_chat_ids() для получения списка ID чатов.
            - Вызывает context.bot.get_chat() для каждого чата для получения названия.
            - Отправляет форматированный список чатов пользователю.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /list_chats от пользователя {user_id}")

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

        chats = context.application.bot_data.get("chats")
        if not chats:
            self.logger.warning("Хранилище чатов не настроено")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Хранилище чатов не настроено",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
            return

        chat_ids = await chats.list_chat_ids()
        if not chat_ids:
            self.logger.info("Нет активных чатов")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Нет активных чатов",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}")
            return

        # Получаем информацию о чатах
        chat_list = []
        for chat_id in chat_ids:
            try:
                chat_info = await context.bot.get_chat(chat_id)
                title = getattr(chat_info, "title", getattr(chat_info, "first_name", "Unknown"))
                chat_list.append(f"• {title} (ID: {chat_id})")
            except Exception as e:
                self.logger.warning(f"Не удалось получить информацию о чате {chat_id}: {e}")
                chat_list.append(f"• Чат {chat_id} (не удалось получить информацию)")

        message = "📋 Активные чаты:\n\n" + "\n".join(chat_list)
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                message,
                max_retries=3,
                delay=2,
            )
            self.logger.info(f"Отправлен список из {len(chat_ids)} активных чатов пользователю {user_id}")
        except Exception as e:
            self.logger.error(f"Не удалось отправить список чатов после {3} попыток: {e}")

    async def set_kandinsky_model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /set_kandinsky_model.

        Устанавливает модель Kandinsky для генерации изображений.
        Можно указать как pipeline_id (число), так и название модели.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к генератору изображений через image_generator.

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
            success, message = await self.image_generator.image_client.set_model(model_arg)
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
                через context.args и к генератору изображений через image_generator.

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

        if not self.image_generator.text_client:
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
            _, message = await self.image_generator.text_client.set_model(model_name)
            await self._retry_on_connect_error(
                update.message.reply_text,
                message,
                max_retries=3,
                delay=2,
            )
        except Exception as e:
            self.logger.error(f"Ошибка при установке модели GigaChat: {e}")

    async def mod_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /mod.

        Предоставляет административные права указанному пользователю.
        Команда доступна только существующим администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args для получения user_id нового администратора.

        Side Effects:
            - Вызывает admins_store.add_admin() для добавления пользователя в список администраторов.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.

        Raises:
            ValueError: Если переданный user_id не является числом.
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
                    "📝 Использование: /mod <user_id>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return

        try:
            user_id = int(context.args[0])
            success = await self.admins_store.add_admin(user_id)
            if success:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ Пользователь {user_id} получил админ-права",
                    max_retries=3,
                    delay=2,
                )
            else:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"ℹ️ Пользователь {user_id} уже является администратором",
                    max_retries=3,
                    delay=2,
                )
        except ValueError:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Неверный user_id (должен быть числом)",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")

    async def unmod_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /unmod.

        Удаляет административные права у указанного пользователя.
        Главного администратора (из .env) удалить нельзя.
        Команда доступна только существующим администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args для получения user_id администратора для удаления.

        Side Effects:
            - Вызывает admins_store.remove_admin() для удаления пользователя из списка администраторов.
            - Отправляет ответное сообщение пользователю с результатом операции.
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.

        Raises:
            ValueError: Если переданный user_id не является числом.
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
                    "📝 Использование: /unmod <user_id>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return

        try:
            user_id = int(context.args[0])
            # Проверяем, не пытаются ли удалить главного админа
            from utils.config import config

            main_admin = config.admin_chat_id
            if main_admin and int(main_admin) == user_id:
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Нельзя удалить главного администратора (из .env)",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
                return

            success = await self.admins_store.remove_admin(user_id)
            if success:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ У пользователя {user_id} удалены админ-права",
                    max_retries=3,
                    delay=2,
                )
            else:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"ℹ️ Пользователь {user_id} не является администратором",
                    max_retries=3,
                    delay=2,
                )
        except ValueError:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Неверный user_id (должен быть числом)",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /list_mods от пользователя {user_id}")

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

        all_admins = await self.admins_store.list_all_admins()
        if not all_admins:
            self.logger.info("Нет администраторов")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Нет администраторов",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}")
            return

        admin_list = []
        from utils.config import config

        main_admin = config.admin_chat_id
        for admin_id in all_admins:
            is_main = " (главный)" if (main_admin and int(main_admin) == admin_id) else ""
            admin_list.append(f"• ID: {admin_id}{is_main}")

        message = "👥 Список администраторов:\n\n" + "\n".join(admin_list)
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                message,
                max_retries=3,
                delay=2,
            )
            self.logger.info(f"Отправлен список из {len(all_admins)} администраторов пользователю {user_id}")
        except Exception as e:
            self.logger.error(f"Не удалось отправить список админов после {3} попыток: {e}")
            raise

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
            await self._retry_on_connect_error(
                update.message.reply_text,
                "❌ Доступно только администратору",
                max_retries=3,
                delay=2,
            )
            return

        try:
            message_parts = ["📋 Доступные модели:\n"]

            # Получаем модели Kandinsky
            try:
                _api_ok, _api_status, api_models, current_kandinsky = await self.image_generator.check_api_status()
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
                if self.image_generator.text_client:
                    gigachat_models = await self.image_generator.text_client.get_available_models()
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
