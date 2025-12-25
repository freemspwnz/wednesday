"""
Базовый класс для обработчиков команд бота.

Содержит общие утилитарные методы, используемые всеми специализированными
наборами хендлеров (UserHandlers, AdminHandlers, ModelHandlers).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path

from telegram import Bot, Message, Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from shared.base.exceptions import RepoError, ServiceError
from shared.bot_services import BotServices, SupportBotServices
from shared.paths import LOGS_DIR
from shared.protocols import ILogger
from shared.retry import retry_on_connect_error

# Константы
MAX_RETRIES_DEFAULT = 3  # количество попыток по умолчанию
RETRY_DELAY_DEFAULT = 2.0  # задержка между попытками по умолчанию
CHAT_INFO_TIMEOUT_DEFAULT = 5.0  # таймаут для получения информации о чате по умолчанию
CHAT_TIMEOUT_DEFAULT = 10.0  # таймаут для получения полного объекта чата по умолчанию


class BaseHandlers:
    """Базовый класс для обработчиков команд с общими утилитарными методами."""

    def __init__(
        self,
        services: BotServices | SupportBotServices,
        logger: ILogger,
    ) -> None:
        """Инициализирует базовый класс обработчиков.

        Args:
            services: Контейнер сервисов бота для доступа к зависимостям.
                Может быть BotServices (для основного бота) или SupportBotServices (для резервного).
            logger: Экземпляр логгера для логирования операций.
        """
        self.logger = logger
        self.services: BotServices | SupportBotServices = services
        # Используем admins_repo из сервисов через DI (ОБЯЗАТЕЛЬНО)
        # SupportBotServices всегда имеет admins_repo, BotServices может иметь None
        if isinstance(services, SupportBotServices):
            self.admins_store = services.admins_repo
        elif services.admins_repo is None:
            raise RuntimeError("admins_repo не инициализирован в BotServices")
        else:
            self.admins_store = services.admins_repo

    async def _send_log_file(self, bot: Bot, chat_id: int, path: Path) -> None:  # noqa: PLR6301
        """Асинхронно читает лог‑файл с диска и отправляет его как документ.

        Чтение файла выполняется в отдельном потоке через run_in_executor,
        чтобы избежать блокировки event loop при работе с файловой системой.
        """
        import asyncio

        loop = asyncio.get_running_loop()

        def _read_bytes(p: Path) -> bytes:
            return p.read_bytes()

        data = await loop.run_in_executor(None, _read_bytes, path)
        await retry_on_connect_error(
            bot.send_document,
            chat_id=chat_id,
            document=data,
            filename=path.name,
            max_retries=3,
            delay=2,
            handle_rate_limit=True,
        )

    async def _extract_target_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
        """Извлекает target_user_id из reply или аргументов команды.

        Проверяет приоритеты:
        1. reply_to_message.from_user.id (если есть reply)
        2. context.args[0] (если ровно один аргумент и это число)

        Args:
            update: Объект обновления Telegram.
            context: Контекст бота с аргументами команды.

        Returns:
            user_id как int, если успешно определён, иначе None.
        """
        # Приоритет 1: reply на сообщение
        if update.message and update.message.reply_to_message:
            reply_user = update.message.reply_to_message.from_user
            if reply_user:
                target_id = int(reply_user.id)
                self.logger.debug(f"_extract_target_user_id: найден через reply: {target_id}")
                return target_id

        # Приоритет 2: аргумент команды
        if context.args:
            if len(context.args) != 1:
                self.logger.debug(
                    f"_extract_target_user_id: неверное количество аргументов: {len(context.args)}",
                )
                return None

            try:
                target_id = int(context.args[0])
                self.logger.debug(f"_extract_target_user_id: найден через аргумент: {target_id}")
                return target_id
            except ValueError as e:
                self.logger.warning(f"_extract_target_user_id: не удалось преобразовать аргумент в int: {e}")
                return None

        return None

    def _is_super_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь главным администратором.

        Сравнивает user_id с settings.admin_chat_id (из .env через DI).

        Args:
            user_id: Идентификатор пользователя для проверки.

        Returns:
            True если user_id совпадает с admin_chat_id, False иначе.
        """
        admin_chat_id = self.services.settings.admin_chat_id
        if not admin_chat_id:
            return False

        return admin_chat_id == user_id

    async def _safe_reply_text(self, message: Message, text: str) -> None:
        """Безопасная отправка текста с retry для Telegram/сетевых ошибок.

        Используется как сокращённая запись для типичного паттерна
        `retry_on_connect_error(message.reply_text, ...)` в местах, где
        не требуется гибкая настройка retry-параметров.

        Обрабатывает ошибки и не пробрасывает исключения - это безопасный метод,
        который не должен прерывать выполнение обработчика.

        Args:
            message: Сообщение для ответа.
            text: Текст для отправки.

        Side Effects:
            - Отправляет сообщение с retry-логикой.
            - Логирует только неожиданные ошибки (не сетевые/Telegram).
            - retry_on_connect_error() уже логирует сетевые ошибки через log_event().
        """
        try:
            await retry_on_connect_error(
                message.reply_text,
                text,
                max_retries=MAX_RETRIES_DEFAULT,
                delay=RETRY_DELAY_DEFAULT,
            )
        except Exception as e:
            # retry_on_connect_error уже залогировал сетевые ошибки через log_event
            # Логируем только если это не сетевая ошибка (неожиданная ошибка)
            if not isinstance(e, TelegramError | NetworkError | TimedOut):
                self.logger.warning(
                    f"Неожиданная ошибка при отправке сообщения: {e}",
                    exc_info=True,
                )
            # Централизованный обработчик перехватит, если это критично

    async def _safe_reply_with_fallback(
        self,
        message: Message,
        text: str,
        fallback_text: str | None = None,
    ) -> bool:
        """Безопасная отправка сообщения с обработкой ошибок.

        Отправляет сообщение с retry-логикой. При ошибке логирует её и
        при необходимости отправляет fallback-сообщение. Не пробрасывает
        исключения - позволяет централизованному обработчику перехватить их.

        Args:
            message: Message объект для отправки ответа.
            text: Текст сообщения для отправки.
            fallback_text: Текст для отправки при ошибке (опционально).

        Returns:
            True если сообщение отправлено успешно, False иначе.

        Side Effects:
            - Отправляет сообщение с retry-логикой.
            - Логирует только неожиданные ошибки (не сетевые/Telegram).
            - retry_on_connect_error() уже логирует сетевые ошибки через log_event().
        """
        try:
            await retry_on_connect_error(
                message.reply_text,
                text,
                max_retries=MAX_RETRIES_DEFAULT,
                delay=RETRY_DELAY_DEFAULT,
            )
            return True
        except Exception as e:
            # retry_on_connect_error уже залогировал сетевые ошибки через log_event
            # Логируем только если это не сетевая ошибка (неожиданная ошибка)
            if not isinstance(e, TelegramError | NetworkError | TimedOut):
                self.logger.warning(
                    f"Неожиданная ошибка при отправке сообщения: {e}",
                    exc_info=True,
                )

            # Если указан fallback текст, пытаемся отправить его
            if fallback_text:
                try:
                    await retry_on_connect_error(
                        message.reply_text,
                        fallback_text,
                        max_retries=MAX_RETRIES_DEFAULT,
                        delay=RETRY_DELAY_DEFAULT,
                    )
                except Exception as fallback_error:
                    # retry_on_connect_error уже залогировал сетевые ошибки
                    # Логируем только неожиданные ошибки
                    if not isinstance(fallback_error, TelegramError | NetworkError | TimedOut):
                        self.logger.warning(
                            f"Неожиданная ошибка при отправке fallback сообщения: {fallback_error}",
                            exc_info=True,
                        )
                    # Централизованный обработчик перехватит, если это критично

            return False

    async def _safe_delete_message(self, message: Message | None) -> None:
        """Безопасно удаляет сообщение, игнорируя ошибки.

        Используется для удаления статусных сообщений, где ошибка удаления
        не критична и не должна прерывать выполнение команды.

        Args:
            message: Сообщение для удаления (может быть None).
        """
        if message is None:
            return

        try:
            await message.delete()
        except Exception as delete_error:
            # Логируем, но не пробрасываем - удаление статусного сообщения не критично
            self.logger.debug(
                f"Не удалось удалить статусное сообщение: {delete_error}",
                exc_info=False,
            )
            # Централизованный обработчик перехватит, если это критично

    async def _safe_reply_text_with_error_logging(
        self,
        message: Message,
        text: str,
        error_context: str = "сообщение",
        max_retries: int = MAX_RETRIES_DEFAULT,
        delay: float = RETRY_DELAY_DEFAULT,
    ) -> bool:
        """Безопасная отправка сообщения с логированием ошибок.

        Отправляет сообщение с retry-логикой и логирует ошибки с полным стеком
        (exc_info=True). Используется в местах, где нужно гарантировать, что
        ошибка отправки не сломает обработчик команды, но нужно логировать
        с полной информацией для диагностики.

        Args:
            message: Message объект для отправки ответа.
            text: Текст сообщения для отправки.
            error_context: Контекст для сообщения об ошибке (например, "об ограничении доступа").
            max_retries: Максимальное количество попыток.
            delay: Задержка между попытками.

        Returns:
            True если сообщение отправлено успешно, False иначе.
        """
        try:
            await retry_on_connect_error(
                message.reply_text,
                text,
                max_retries=max_retries,
                delay=delay,
            )
            return True
        except Exception as e:
            # Exception оправдан - нужно гарантировать, что ошибка отправки не сломает обработчик
            self.logger.error(
                f"Не удалось отправить {error_context} после {max_retries} попыток: {e}",
                exc_info=True,
            )
            return False

    async def _handle_command_errors(
        self,
        update: Update,
        func: Callable[[], Awaitable[None]],
    ) -> None:
        """Универсальный обработчик ошибок для команд.

        Обеспечивает единообразную обработку ошибок во всех командах:
        - Ошибки валидации данных (ValueError, TypeError, AttributeError)
        - Сетевые ошибки Telegram API (TelegramError, NetworkError, TimedOut)
        - Ошибки сервисного слоя (ServiceError)
        - Ошибки репозитория (RepoError)
        - Критические ошибки пробрасываются выше

        Args:
            update: Объект обновления Telegram.
            func: Асинхронная функция для выполнения команды.

        Side Effects:
            - Логирует ошибки с соответствующими уровнями (warning/error).
            - Отправляет сообщения об ошибках пользователю через _safe_reply_with_fallback().
            - Критические ошибки (память, системные) пробрасываются выше.
        """
        try:
            await func()
        except (ValueError, TypeError, AttributeError) as e:
            # Ошибки валидации данных или доступа к атрибутам
            self.logger.error(f"Ошибка валидации: {e}", exc_info=True)
            if update.message:
                await self._safe_reply_with_fallback(
                    update.message,
                    "❌ Ошибка валидации данных",
                )
        except (TelegramError, NetworkError, TimedOut) as e:
            # Сетевые ошибки Telegram API
            self.logger.warning(f"Сетевая ошибка Telegram API: {e}")
            if update.message:
                await self._safe_reply_with_fallback(
                    update.message,
                    "❌ Временная проблема с Telegram API. Попробуйте позже.",
                )
        except ServiceError as e:
            # Ошибки сервисного слоя
            self.logger.error(f"Ошибка сервиса: {e}", exc_info=True)
            if update.message:
                await self._safe_reply_with_fallback(
                    update.message,
                    f"❌ Ошибка сервиса: {str(e)[:200]}",
                )
        except RepoError as e:
            # Ошибки репозитория
            self.logger.error(f"Ошибка репозитория: {e}", exc_info=True)
            if update.message:
                await self._safe_reply_with_fallback(
                    update.message,
                    f"❌ Ошибка доступа к данным: {str(e)[:200]}",
                )
        except asyncio.CancelledError:
            # Задача была отменена (например, при остановке бота)
            self.logger.info("Команда была отменена")
            raise  # Пробрасываем дальше для корректной обработки
        # Критические ошибки (память, системные) должны пробрасываться выше

    async def _gather_with_timeout(
        self,
        *tasks: Awaitable,
        timeout: float | None = None,
        return_exceptions: bool = True,
    ) -> list:
        """Выполняет asyncio.gather с таймаутом для всех задач.

        Оборачивает каждую задачу в asyncio.wait_for для защиты от зависаний.
        Если таймаут не указан, используется значение по умолчанию.

        Args:
            *tasks: Асинхронные задачи для параллельного выполнения.
            timeout: Таймаут для каждой задачи в секундах. Если None, используется
                CHAT_INFO_TIMEOUT_DEFAULT.
            return_exceptions: Если True, исключения возвращаются как результаты,
                а не пробрасываются.

        Returns:
            Список результатов выполнения задач. Если return_exceptions=True,
            исключения включаются в список как элементы.

        Side Effects:
            - Логирует предупреждения при таймаутах.
            - Защищает от зависания при проблемах с сетью.
        """
        if timeout is None:
            timeout = CHAT_INFO_TIMEOUT_DEFAULT

        async def _with_timeout(task: Awaitable) -> object:
            """Оборачивает задачу в таймаут."""
            try:
                return await asyncio.wait_for(task, timeout=timeout)
            except TimeoutError as e:
                self.logger.warning(f"Таймаут {timeout}с при выполнении задачи")
                if return_exceptions:
                    return e
                raise

        wrapped_tasks = [_with_timeout(task) for task in tasks]
        return await asyncio.gather(*wrapped_tasks, return_exceptions=return_exceptions)

    async def _send_logs_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        max_days: int = 10,
    ) -> None:
        """Общая логика отправки логов для команды /log.

        Отправляет логи администратору. Без аргумента отправляет последний файл,
        с аргументом [count] отправляет логи за N дней (1..max_days).

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к боту для отправки файлов через context.bot.
            max_days: Максимальное количество дней для отправки логов (по умолчанию 10).

        Side Effects:
            - Читает файлы логов из директории logs/.
            - Отправляет файлы логов в чат через context.bot.send_document().
            - Проверяет права администратора через admins_store.is_admin().
        """
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = update.effective_user.id
        if not await self.admins_store.is_admin(user_id):
            try:
                await retry_on_connect_error(
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
                await retry_on_connect_error(
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
                    await retry_on_connect_error(
                        update.message.reply_text,
                        f"❌ Неверный аргумент. Используйте: /log [count], где count — число 1..{max_days}",
                        max_retries=3,
                        delay=2,
                    )
                except (TelegramError, NetworkError, TimedOut):
                    pass
                return
            count = int(raw)
            if count > max_days:
                count = max_days
                capped_note = f"(ограничено максимумом {max_days} дней)"

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
                await retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Нет логов для отправки",
                    max_retries=3,
                    delay=2,
                )
            except (TelegramError, NetworkError, TimedOut):
                pass
            return

        try:
            await retry_on_connect_error(
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
            await retry_on_connect_error(
                update.message.reply_text,
                "✅ Готово",
                max_retries=3,
                delay=2,
            )
        except (TelegramError, NetworkError, TimedOut):
            pass
