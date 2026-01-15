"""
Базовый класс для обработчиков команд бота.

Содержит общие утилитарные методы, используемые всеми специализированными
наборами хендлеров (UserHandlers, AdminHandlers, ModelHandlers).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from telegram import Message, Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from shared.base.exceptions import RepoError, ServiceError
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger
from shared.retry import retry_on_connect_error

if TYPE_CHECKING:
    from app.image_service import ImageService

# Константы
MAX_RETRIES_DEFAULT = 3  # количество попыток по умолчанию
RETRY_DELAY_DEFAULT = 2.0  # задержка между попытками по умолчанию
CHAT_INFO_TIMEOUT_DEFAULT = 5.0  # таймаут для получения информации о чате по умолчанию
CHAT_TIMEOUT_DEFAULT = 10.0  # таймаут для получения полного объекта чата по умолчанию
MAX_RETRIES_LIMIT = 5  # максимальное количество попыток для защиты от утечек памяти
COMMAND_TIMEOUT_DEFAULT = 60.0  # таймаут для выполнения команды по умолчанию (60 секунд)


class BaseHandlers:
    """Базовый класс для обработчиков команд с общими утилитарными методами."""

    def __init__(
        self,
        services: BotServices,
        logger: ILogger,
    ) -> None:
        """Инициализирует базовый класс обработчиков.

        Args:
            services: Контейнер сервисов бота для доступа к зависимостям.
            logger: Экземпляр логгера для логирования операций.
        """
        self.logger = logger
        self.services: BotServices = services
        # Используем admins_repo из сервисов через DI (ОБЯЗАТЕЛЬНО)
        if services.admins_repo is None:
            raise RuntimeError("admins_repo не инициализирован в BotServices")
        self.admins_store = services.admins_repo

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

    async def _is_super_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь главным администратором.

        Делегирует проверку в admin_access_service.

        Args:
            user_id: Идентификатор пользователя для проверки.

        Returns:
            True если user_id является главным администратором, False иначе.
        """
        if self.services.admin_access_service:
            return await self.services.admin_access_service.is_super_admin(user_id)
        # Fallback для обратной совместимости
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
        Использует rate limiting для защиты от превышения лимитов Telegram API.

        Args:
            message: Сообщение для ответа.
            text: Текст для отправки.

        Side Effects:
            - Отправляет сообщение с retry-логикой и rate limiting.
            - Логирует только неожиданные ошибки (не сетевые/Telegram).
            - retry_on_connect_error() уже логирует сетевые ошибки через log_event().
        """
        try:
            # Получаем rate limiter через services (если доступен)
            rate_limiter = getattr(self.services, "telegram_api_rate_limiter", None)

            async def _reply() -> None:
                await retry_on_connect_error(
                    message.reply_text,
                    text,
                    max_retries=MAX_RETRIES_DEFAULT,
                    delay=RETRY_DELAY_DEFAULT,
                )

            if rate_limiter:
                await rate_limiter.execute_with_rate_limit(_reply)
            else:
                # Fallback без rate limiting (для обратной совместимости)
                await _reply()
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
        Использует rate limiting для защиты от превышения лимитов Telegram API.

        Args:
            message: Message объект для отправки ответа.
            text: Текст сообщения для отправки.
            fallback_text: Текст для отправки при ошибке (опционально).

        Returns:
            True если сообщение отправлено успешно, False иначе.

        Side Effects:
            - Отправляет сообщение с retry-логикой и rate limiting.
            - Логирует только неожиданные ошибки (не сетевые/Telegram).
            - retry_on_connect_error() уже логирует сетевые ошибки через log_event().
        """
        try:
            # Получаем rate limiter через services (если доступен)
            rate_limiter = getattr(self.services, "telegram_api_rate_limiter", None)

            async def _reply() -> None:
                await retry_on_connect_error(
                    message.reply_text,
                    text,
                    max_retries=MAX_RETRIES_DEFAULT,
                    delay=RETRY_DELAY_DEFAULT,
                )

            if rate_limiter:
                await rate_limiter.execute_with_rate_limit(_reply)
            else:
                # Fallback без rate limiting (для обратной совместимости)
                await _reply()
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
                    rate_limiter = getattr(self.services, "telegram_api_rate_limiter", None)

                    async def _reply_fallback() -> None:
                        await retry_on_connect_error(
                            message.reply_text,
                            fallback_text,
                            max_retries=MAX_RETRIES_DEFAULT,
                            delay=RETRY_DELAY_DEFAULT,
                        )

                    if rate_limiter:
                        await rate_limiter.execute_with_rate_limit(_reply_fallback)
                    else:
                        # Fallback без rate limiting (для обратной совместимости)
                        await _reply_fallback()
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
        except (TelegramError, NetworkError, TimedOut) as delete_error:
            # Сетевые ошибки Telegram API - логируем, но не прерываем
            self.logger.debug(
                f"Не удалось удалить статусное сообщение (сетевая ошибка): {delete_error}",
                exc_info=False,
            )
        except Exception as delete_error:
            # Неожиданные ошибки - логируем с полным стеком для диагностики
            self.logger.warning(
                f"Неожиданная ошибка при удалении статусного сообщения: {delete_error}",
                exc_info=True,
            )

    def _handle_send_message_error(
        self,
        error: Exception,
        context: str = "отправке сообщения",
    ) -> None:
        """Обрабатывает ошибки отправки сообщений с правильным логированием.

        Разделяет обработку сетевых ошибок Telegram API и неожиданных ошибок.
        Используется для замены `except Exception: pass` на более специфичную обработку.

        Args:
            error: Исключение, которое произошло при отправке сообщения.
            context: Контекст для логирования (например, "отправке сообщения об ошибке").
        """
        if isinstance(error, TelegramError | NetworkError | TimedOut):
            # Сетевые ошибки Telegram API - логируем, но не прерываем
            self.logger.warning(
                f"Сетевая ошибка Telegram API при {context}: {error}",
                exc_info=False,
            )
        else:
            # Неожиданные ошибки - логируем с полным стеком для диагностики
            self.logger.error(
                f"Неожиданная ошибка при {context}: {error}",
                exc_info=True,
            )

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
        Использует rate limiting для защиты от превышения лимитов Telegram API.

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
            # Получаем rate limiter через services (если доступен)
            rate_limiter = getattr(self.services, "telegram_api_rate_limiter", None)

            async def _reply() -> None:
                await retry_on_connect_error(
                    message.reply_text,
                    text,
                    max_retries=max_retries,
                    delay=delay,
                )

            if rate_limiter:
                await rate_limiter.execute_with_rate_limit(_reply)
            else:
                # Fallback без rate limiting (для обратной совместимости)
                await _reply()
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
        max_retries: int = 1,
        timeout: float | None = None,
    ) -> None:
        """Универсальный обработчик ошибок для команд с защитой от утечек памяти.

        Обеспечивает единообразную обработку ошибок во всех командах:
        - Ошибки валидации данных (ValueError, TypeError, AttributeError) - не ретраим
        - Сетевые ошибки Telegram API (TelegramError, NetworkError, TimedOut) - ретраим с ограничением
        - Ошибки сервисного слоя (ServiceError) - не ретраим
        - Ошибки репозитория (RepoError) - не ретраим
        - Критические ошибки пробрасываются выше

        Args:
            update: Объект обновления Telegram.
            func: Асинхронная функция для выполнения команды.
            max_retries: Максимальное количество попыток для сетевых ошибок (по умолчанию 1,
                что означает без retry). Используется только для сетевых ошибок Telegram API.
            timeout: Таймаут для выполнения команды в секундах. Если None, таймаут не применяется.
                Если указан, команда будет прервана после истечения времени с сообщением об ошибке.

        Side Effects:
            - Логирует ошибки с соответствующими уровнями (warning/error).
            - Отправляет сообщения об ошибках пользователю через _safe_reply_with_fallback().
            - Критические ошибки (память, системные) пробрасываются выше.
            - Защита от утечек памяти: явное ограничение количества попыток, не накапливает исключения.
            - Защита от зависаний: таймаут прерывает выполнение команды при превышении времени.

        Note:
            Retry выполняется только для сетевых ошибок Telegram API. Ошибки валидации,
            сервисного слоя и репозитория не ретраятся, так как они не являются временными.
            По умолчанию max_retries=1 означает "без retry", что безопасно для команд,
            которые уже используют retry_on_connect_error для сетевых операций.
        """
        # Защита от некорректных значений max_retries
        max_retries = max(max_retries, 1)
        if max_retries > MAX_RETRIES_LIMIT:
            # Ограничиваем максимальное количество попыток для защиты от утечек памяти
            self.logger.warning(
                f"max_retries={max_retries} слишком большой, ограничиваем до {MAX_RETRIES_LIMIT}",
            )
            max_retries = MAX_RETRIES_LIMIT

        async def _execute_with_retries() -> None:
            """Внутренняя функция для выполнения команды с retry-логикой."""
            attempt = 0
            last_network_error: Exception | None = None

            while attempt < max_retries:
                try:
                    await func()
                    return  # Успех - выходим
                except (ValueError, TypeError, AttributeError) as e:
                    # Ошибки валидации данных или доступа к атрибутам - не ретраим
                    self.logger.error(f"Ошибка валидации: {e}", exc_info=True)
                    if update.message:
                        await self._safe_reply_with_fallback(
                            update.message,
                            "❌ Ошибка валидации данных",
                        )
                    return  # Не ретраим ошибки валидации
                except (TelegramError, NetworkError, TimedOut) as e:
                    # Сетевые ошибки Telegram API - ретраим с ограничением
                    attempt += 1
                    last_network_error = e

                    if attempt < max_retries:
                        # Есть еще попытки - делаем retry с экспоненциальным backoff
                        wait_time = RETRY_DELAY_DEFAULT * attempt
                        self.logger.warning(
                            f"Сетевая ошибка Telegram API (попытка {attempt}/{max_retries}): {e}. "
                            f"Повтор через {wait_time}с",
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    # Все попытки исчерпаны
                    self.logger.warning(f"Сетевая ошибка Telegram API после {max_retries} попыток: {e}")
                    if update.message:
                        await self._safe_reply_with_fallback(
                            update.message,
                            "❌ Временная проблема с Telegram API. Попробуйте позже.",
                        )
                    return
                except ServiceError as e:
                    # Ошибки сервисного слоя - не ретраим
                    self.logger.error(f"Ошибка сервиса: {e}", exc_info=True)
                    if update.message:
                        await self._safe_reply_with_fallback(
                            update.message,
                            f"❌ Ошибка сервиса: {str(e)[:200]}",
                        )
                    return  # Не ретраим ошибки сервиса
                except RepoError as e:
                    # Ошибки репозитория - не ретраим
                    self.logger.error(f"Ошибка репозитория: {e}", exc_info=True)
                    if update.message:
                        await self._safe_reply_with_fallback(
                            update.message,
                            f"❌ Ошибка доступа к данным: {str(e)[:200]}",
                        )
                    return  # Не ретраим ошибки репозитория
                except asyncio.CancelledError:
                    # Задача была отменена (например, при остановке бота)
                    self.logger.info("Команда была отменена")
                    raise  # Пробрасываем дальше для корректной обработки
                # Критические ошибки (память, системные) должны пробрасываться выше

            # Если дошли сюда, все попытки исчерпаны (не должно произойти, но защита)
            if last_network_error:
                self.logger.error(
                    f"Все {max_retries} попыток исчерпаны для сетевой ошибки: {last_network_error}",
                )
                if update.message:
                    await self._safe_reply_with_fallback(
                        update.message,
                        "❌ Временная проблема с Telegram API. Попробуйте позже.",
                    )

        # Применяем таймаут, если указан
        if timeout is not None:
            try:
                await asyncio.wait_for(_execute_with_retries(), timeout=timeout)
            except TimeoutError:
                self.logger.error(
                    f"Команда не завершилась за {timeout}с, прерываем выполнение",
                    exc_info=False,
                )
                if update.message:
                    await self._safe_reply_with_fallback(
                        update.message,
                        "❌ Команда заняла слишком много времени. Попробуйте позже.",
                    )
            except asyncio.CancelledError:
                # Пробрасываем CancelledError дальше для корректной обработки
                raise
        else:
            # Выполняем без таймаута
            await _execute_with_retries()

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

    @staticmethod
    async def _handle_image_generation_errors(
        image_service: ImageService,
        user_id: int,
    ) -> tuple[bytes | None, str, bool]:
        """Обрабатывает ошибки генерации изображений с fallback.

        Делегирует генерацию с fallback в image_service.generate_or_fallback().

        Args:
            image_service: Сервис для генерации изображений.
            user_id: ID пользователя для генерации изображения.

        Returns:
            Кортеж (image_data, caption, use_fallback), где:
            - image_data: Данные изображения в байтах или None
            - caption: Подпись к изображению
            - use_fallback: True если используется fallback, False если новое изображение

        Note:
            Этот метод является обёрткой для обратной совместимости.
            Рекомендуется использовать image_service.generate_or_fallback() напрямую.
        """
        return await image_service.generate_or_fallback(user_id=user_id)
