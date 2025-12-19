from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from telegram import Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from bot.base_handlers import BaseHandlers
from services.application.admin_dashboard_service import AdminDashboardService
from services.bot_services import BotServices
from utils.paths import LOGS_DIR

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
        services: BotServices,
    ) -> None:
        super().__init__(services)
        self._dashboard_service = AdminDashboardService(
            usage=self.services.usage,
            chats=self.services.chats,
            metrics=self.services.metrics,
        )

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
            bot_info = await context.bot.get_me()
            status_message = await self._dashboard_service.build_status_message(
                bot_name=bot_info.first_name,
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
            except (TelegramError, NetworkError, TimedOut):
                pass
            return

        logs_dir = LOGS_DIR
        if not logs_dir.exists():
            try:
                self.logger.info(
                    f"Запрошена команда /log, но директория логов отсутствует: {logs_dir}",
                )
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Папка logs пуста или отсутствует",
                    max_retries=3,
                    delay=2,
                )
            except (TelegramError, NetworkError, TimedOut):
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
                except (TelegramError, NetworkError, TimedOut):
                    pass
                return
            count = int(raw)
            if count > MAX_LOG_DAYS:
                count = MAX_LOG_DAYS
                capped_note = f"(ограничено максимумом {MAX_LOG_DAYS} дней)"

        # Определяем файлы по датам за count дней, учитывая .log и .log.zip
        wanted_dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(count)]
        candidates: list[Path] = []
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
            except (TelegramError, NetworkError, TimedOut):
                pass
            return

        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                f"📦 Отправляю файл(ы) логов за {len(candidates)} дн. {capped_note or ''}",
                max_retries=3,
                delay=2,
            )
        except (TelegramError, NetworkError, TimedOut):
            pass

        # Отправляем в порядке от старых к новым
        for lf in sorted(candidates, key=lambda p: p.name):
            try:
                self.logger.info(f"Отправляю лог-файл {lf}")
                await self._send_log_file(
                    bot=context.bot,
                    chat_id=update.effective_chat.id,
                    path=lf,
                )
            except (TelegramError, NetworkError, TimedOut) as e:
                self.logger.warning(f"Ошибка при отправке лога {lf}: {e}")
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                "✅ Готово",
                max_retries=3,
                delay=2,
            )
        except (TelegramError, NetworkError, TimedOut):
            pass

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
            admin_chat_id = self.services.settings.admin_chat_id
            if admin_chat_id and update.effective_chat and update.effective_chat.id is not None:
                try:
                    is_admin_chat = admin_chat_id == update.effective_chat.id
                except (ValueError, TypeError, AttributeError):
                    is_admin_chat = False
        except (ValueError, TypeError, AttributeError):
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
            except (TelegramError, NetworkError, TimedOut):
                status_msg = None

        # Сохраняем метаданные сообщения в экземпляр основного бота (только для не-админ чатов)
        try:
            bot_controller = self.services.bot_controller
            if (not is_admin_chat) and bot_controller is not None and status_msg is not None and update.effective_chat:
                bot_controller.pending_shutdown_edit = {
                    "chat_id": update.effective_chat.id,
                    "message_id": getattr(status_msg, "message_id", None),
                }
        except (ValueError, TypeError, AttributeError):
            pass

        # Получаем экземпляр основного бота через DI и останавливаем его
        try:
            bot_controller = self.services.bot_controller
            if bot_controller is not None:
                await bot_controller.stop()
            else:
                # Фоллбек: попытаться аккуратно остановить приложение
                try:
                    if hasattr(context.application, "updater") and context.application.updater:
                        await context.application.updater.stop()
                except Exception as e:
                    self.logger.warning(f"Ошибка при остановке updater через фоллбек: {e}", exc_info=True)
                try:
                    await context.application.stop()
                except Exception as e:
                    self.logger.warning(f"Ошибка при остановке application через фоллбек: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Ошибка при попытке остановить бота через /stop: {e}", exc_info=True)

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
            except (TelegramError, NetworkError, TimedOut) as e:
                self.logger.error(f"Не удалось отправить сообщение об ограничении доступа после {3} попыток: {e}")
            return

        chats = self.services.chats
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
            except (TelegramError, NetworkError, TimedOut) as e:
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
                except (TelegramError, NetworkError, TimedOut) as e:
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
                    try:
                        await self._retry_on_connect_error(
                            update.message.reply_text,
                            f"❌ Чат {requested_chat_id} не найден в списке активных чатов",
                            max_retries=3,
                            delay=2,
                        )
                    except (TelegramError, NetworkError, TimedOut) as e:
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
                except (TelegramError, NetworkError, TimedOut) as e:
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
            except (TelegramError, NetworkError, TimedOut) as e:
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
        except (TelegramError, NetworkError, TimedOut) as e:
            self.logger.error(f"Не удалось отправить статусное сообщение после {3} попыток: {e}")
            status_msg = None

        # Генерируем или получаем изображение
        image_data: bytes | None = None
        caption: str = ""
        use_fallback = False

        image_service = self.services.image_service
        if can_generate and image_service is not None:
            try:
                result = await image_service.generate_frog_image(user_id=user_id)
                if result:
                    image_data, caption = result
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
            if image_service is not None:
                fallback_image = await image_service.get_random_saved_image()
            else:
                fallback_image = None
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
        admin_chat_id = self.services.settings.admin_chat_id
        if admin_chat_id:
            try:
                await self._retry_on_connect_error(
                    context.bot.send_photo,
                    chat_id=admin_chat_id,
                    photo=image_data,
                    caption=f"🐸 Принудительная отправка (команда /force_send)\n\n{caption}",
                    max_retries=3,
                    delay=2,
                )
                self.logger.info(f"Изображение отправлено главному админу {admin_chat_id}")
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
                через context.args. Хранилище чатов берётся из self.services.chats.

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
            chats = self.services.chats
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
                    "📝 Использование: /remove_chat <chat_id>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return

        try:
            chat_id = int(context.args[0])
            chats = self.services.chats
            await chats.remove_chat(chat_id)
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ Чат {chat_id} удалён из рассылки",
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

        chats = self.services.chats
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
        if not context.args or len(context.args) < 1:
            self.logger.warning("set_frog_limit_command: аргументы не предоставлены")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"📝 Использование: /set_frog_limit <threshold> (1..{MAX_FROG_THRESHOLD})",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return
        try:
            raw = int(context.args[0])
            self.logger.info(f"set_frog_limit_command: запрошенный порог: {raw}")
            if raw <= 0:
                raise ValueError(f"Порог должен быть положительным числом, получено: {raw}")
            # Ограничим максимумом MAX_FROG_THRESHOLD
            desired = min(raw, MAX_FROG_THRESHOLD)
            usage = self.services.usage
            if usage:
                new_threshold = await usage.set_frog_threshold(desired)
                total, _threshold, quota = await usage.get_limits_info()
                self.logger.info(
                    f"set_frog_limit_command: порог установлен на {new_threshold}, использование: {total}/{quota}",
                )
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        f"✅ Порог /frog установлен: {new_threshold} (текущее использование: {total}/{quota})",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об успехе после {3} попыток: {e}")
                self.logger.info("set_frog_limit_command: команда выполнена успешно")
            else:
                self.logger.error("set_frog_limit_command: хранилище использования не инициализировано")
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Хранилище использования не инициализировано",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
        except ValueError as e:
            self.logger.error(f"set_frog_limit_command: ошибка валидации параметра: {e}", exc_info=True)
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Неверный параметр. Использование: /set_frog_limit <threshold> (1..{MAX_FROG_THRESHOLD})",
                    max_retries=3,
                    delay=2,
                )
            except Exception as send_error:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {send_error}")
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
        if not context.args or len(context.args) < 1:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📝 Использование: /set_frog_used <count>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return
        try:
            raw = int(context.args[0])
            if raw < 0:
                raise ValueError
            usage = self.services.usage
            if usage:
                # Ограничим значением квоты
                capped = min(raw, usage.monthly_quota)
                await usage.set_month_total(capped)
                total, threshold, quota = await usage.get_limits_info()
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        f"✅ Текущее использование /frog: {total}/{threshold} (квота: {quota})",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об успехе после {3} попыток: {e}")
            else:
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Хранилище использования не инициализировано",
                        max_retries=3,
                        delay=2,
                    )
                except Exception as e:
                    self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")
        except ValueError:
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Неверный параметр. Использование: /set_frog_used <count>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ошибке после {3} попыток: {e}")

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /mod от пользователя {user_id}")

        # Проверка прав: только главный администратор
        if not self._is_super_admin(user_id):
            self.logger.warning(f"mod_command: пользователь {user_id} не является главным администратором")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Доступно только главному администратору",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ограничении доступа после {3} попыток: {e}")
            return

        # Извлекаем target_user_id из reply или аргументов
        target_user_id = await self._extract_target_user_id(update, context)

        if target_user_id is None:
            self.logger.warning("mod_command: не удалось определить target_user_id")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📝 Использование: ответьте на сообщение пользователя командой /mod или вызовите: /mod <user_id>",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об использовании команды после {3} попыток: {e}")
            return

        self.logger.info(f"mod_command: попытка добавить админа {target_user_id} пользователем {user_id}")

        # Добавляем администратора
        success = await self.admins_store.add_admin(target_user_id)
        if success:
            self.logger.info(f"mod_command: пользователь {target_user_id} успешно добавлен как администратор")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ Пользователь {target_user_id} получил админ‑права",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об успехе после {3} попыток: {e}")
        else:
            self.logger.info(f"mod_command: пользователь {target_user_id} уже является администратором")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"ℹ️ Пользователь {target_user_id} уже является администратором",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}")

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
            - Использует _retry_on_connect_error() для обработки сетевых ошибок.
        """
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.logger.info(f"Получена команда /unmod от пользователя {user_id}")

        # Проверка прав: только главный администратор
        if not self._is_super_admin(user_id):
            self.logger.warning(f"unmod_command: пользователь {user_id} не является главным администратором")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "❌ Доступно только главному администратору",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об ограничении доступа после {3} попыток: {e}")
            return

        # Извлекаем target_user_id из reply или аргументов
        target_user_id = await self._extract_target_user_id(update, context)

        # Если target_user_id не определён - показываем список админов
        if target_user_id is None:
            self.logger.info("unmod_command: target_user_id не определён, показываем список админов")
            try:
                admins = await self.admins_store.list_all_admins()
                if not admins:
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
                for admin_id in admins:
                    try:
                        chat = await context.bot.get_chat(admin_id)
                        # Формируем имя с разумным fallback
                        name_parts = []
                        if hasattr(chat, "full_name") and chat.full_name:
                            name_parts.append(chat.full_name)
                        elif hasattr(chat, "first_name") and chat.first_name:
                            name_parts.append(chat.first_name)
                        name = " ".join(name_parts) if name_parts else "Unknown"

                        # Добавляем username если есть
                        username_text = ""
                        if hasattr(chat, "username") and chat.username:
                            username_text = f" (@{chat.username})"

                        # Помечаем главного админа
                        is_main = " (главный)" if self._is_super_admin(admin_id) else ""

                        admin_list.append(f"• ID: {admin_id} ({name}{username_text}){is_main}")
                    except Exception as e:
                        self.logger.warning(f"Не удалось получить информацию о чате {admin_id}: {e}")
                        is_main = " (главный)" if self._is_super_admin(admin_id) else ""
                        admin_list.append(f"• ID: {admin_id} (не удалось получить информацию){is_main}")

                message = "👥 Список администраторов:\n\n" + "\n".join(admin_list)
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        message,
                        max_retries=3,
                        delay=2,
                    )
                    self.logger.info(f"Отправлен список из {len(admins)} администраторов пользователю {user_id}")
                except Exception as e:
                    self.logger.error(f"Не удалось отправить список админов после {3} попыток: {e}")
            except Exception as e:
                self.logger.error(f"Ошибка при получении списка админов: {e}", exc_info=True)
                try:
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Ошибка при получении списка администраторов",
                        max_retries=3,
                        delay=2,
                    )
                except Exception:
                    pass
            return

        # Ветка удаления админа
        self.logger.info(f"unmod_command: попытка удалить админа {target_user_id} пользователем {user_id}")

        # Проверяем, не пытаются ли удалить главного админа
        if self._is_super_admin(target_user_id):
            self.logger.warning(f"unmod_command: попытка удалить главного администратора {target_user_id}")
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

        # Удаляем админа
        success = await self.admins_store.remove_admin(target_user_id)
        if success:
            self.logger.info(f"unmod_command: пользователь {target_user_id} успешно удалён из админов")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"✅ У пользователя {target_user_id} удалены админ‑права",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение об успехе после {3} попыток: {e}")
        else:
            self.logger.info(f"unmod_command: пользователь {target_user_id} не является администратором")
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"ℹ️ Пользователь {target_user_id} не является администратором",
                    max_retries=3,
                    delay=2,
                )
            except Exception as e:
                self.logger.error(f"Не удалось отправить сообщение после {3} попыток: {e}")

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
        main_admin = self.services.settings.admin_chat_id
        for admin_id in all_admins:
            is_main = " (главный)" if (main_admin and main_admin == admin_id) else ""
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
