"""
Базовый класс для обработчиков команд бота.

Содержит общие утилитарные методы, используемые всеми специализированными
наборами хендлеров (UserHandlers, AdminHandlers, ModelHandlers).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from telegram import Message, Update, User
from telegram.ext import ContextTypes

from shared.bot_services import BotServices
from shared.constants import (
    CHAT_INFO_TIMEOUT_DEFAULT,
    MAX_RETRIES_DEFAULT,
    RETRY_DELAY_DEFAULT,
)
from shared.protocols.infrastructure import ILogger
from shared.retry import retry_on_connect_error
from shared.utils.async_utils import gather_with_timeout


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
        if services.telegram_api_rate_limiter is None:
            raise ValueError("telegram_api_rate_limiter must be provided in BotServices")
        if services.command_error_handler is None:
            raise ValueError("command_error_handler must be provided in BotServices")
        # Сохраняем в локальные переменные для типизации mypy
        self._rate_limiter = services.telegram_api_rate_limiter
        self._command_error_handler = services.command_error_handler

    def _validate_update(self, update: Update) -> tuple[Message, User] | None:  # noqa: PLR6301
        """Валидирует update и возвращает message и user или None.

        Устраняет дублирование проверок update.message и update.effective_user
        во всех обработчиках.

        Args:
            update: Объект обновления Telegram.

        Returns:
            Кортеж (message, user) если валидация прошла, None иначе.
        """
        if not update.message or not update.effective_user:
            return None
        return update.message, update.effective_user

    async def _extract_target_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
        """Извлекает target_user_id из reply или аргументов команды.

        Делегирует извлечение в UserExtractionService для соблюдения границ слоёв.

        Args:
            update: Объект обновления Telegram.
            context: Контекст бота с аргументами команды.

        Returns:
            user_id как int, если успешно определён, иначе None.
        """
        if self.services.user_extraction_service is None:
            raise ValueError("user_extraction_service must be provided in BotServices")
        return self.services.user_extraction_service.extract_target_user_id(update, context)

    def _has_args(self, context: ContextTypes.DEFAULT_TYPE, min_count: int = 1) -> bool:
        """Проверяет наличие аргументов команды.

        Делегирует проверку в CommandValidationService для соблюдения границ слоёв.

        Args:
            context: Контекст бота с аргументами команды.
            min_count: Минимальное количество аргументов (по умолчанию 1).

        Returns:
            True если аргументы присутствуют и их количество >= min_count, False иначе.
        """
        if self.services.command_validation_service is None:
            raise ValueError("command_validation_service must be provided in BotServices")
        return self.services.command_validation_service.has_args(context, min_count)

    def _require_admin_access_service(self) -> None:
        """Проверяет наличие admin_access_service.

        Raises:
            ValueError: Если admin_access_service не предоставлен.
        """
        if self.services.admin_access_service is None:
            raise ValueError("admin_access_service must be provided in BotServices")

    async def _check_admin_access(
        self,
        user_id: int,
        message: Message,
        require_super: bool = False,
    ) -> bool:
        """Проверяет доступ администратора и отправляет сообщение об ошибке при отсутствии доступа.

        Args:
            user_id: ID пользователя для проверки.
            message: Сообщение для отправки ответа об ошибке.
            require_super: Если True, проверяет доступ главного администратора.

        Returns:
            True если доступ есть, False если доступ отсутствует (сообщение об ошибке отправлено).
        """
        self._require_admin_access_service()
        admin_access = self.services.admin_access_service
        assert admin_access is not None  # для mypy

        is_authorized, error_message = await admin_access.check_admin_access_with_message(user_id, require_super)
        if not is_authorized:
            await self._safe_reply_with_fallback(message, error_message)
            return False
        return True

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

            async def _reply() -> None:
                await retry_on_connect_error(
                    message.reply_text,
                    text,
                    max_retries=MAX_RETRIES_DEFAULT,
                    delay=RETRY_DELAY_DEFAULT,
                )

            await self._rate_limiter.execute_with_rate_limit(_reply)
        except Exception as e:
            # retry_on_connect_error уже залогировал сетевые ошибки через log_event
            # Логируем только если это не сетевая ошибка (неожиданная ошибка)
            if self.services.error_classification_service is None:
                raise ValueError("error_classification_service must be provided in BotServices") from None
            if not self.services.error_classification_service.is_telegram_error(e):
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

            async def _reply() -> None:
                await retry_on_connect_error(
                    message.reply_text,
                    text,
                    max_retries=MAX_RETRIES_DEFAULT,
                    delay=RETRY_DELAY_DEFAULT,
                )

            await self._rate_limiter.execute_with_rate_limit(_reply)
            return True
        except Exception as e:
            # retry_on_connect_error уже залогировал сетевые ошибки через log_event
            # Логируем только если это не сетевая ошибка (неожиданная ошибка)
            if self.services.error_classification_service is None:
                raise ValueError("error_classification_service must be provided in BotServices") from None
            if not self.services.error_classification_service.is_telegram_error(e):
                self.logger.warning(
                    f"Неожиданная ошибка при отправке сообщения: {e}",
                    exc_info=True,
                )

            # Если указан fallback текст, пытаемся отправить его
            if fallback_text:
                try:

                    async def _reply_fallback() -> None:
                        await retry_on_connect_error(
                            message.reply_text,
                            fallback_text,
                            max_retries=MAX_RETRIES_DEFAULT,
                            delay=RETRY_DELAY_DEFAULT,
                        )

                    await self._rate_limiter.execute_with_rate_limit(_reply_fallback)
                except Exception as fallback_error:
                    # retry_on_connect_error уже залогировал сетевые ошибки
                    # Логируем только неожиданные ошибки
                    if not self.services.error_classification_service.is_telegram_error(fallback_error):
                        self.logger.warning(
                            f"Неожиданная ошибка при отправке fallback сообщения: {fallback_error}",
                            exc_info=True,
                        )
                    # Централизованный обработчик перехватит, если это критично

            return False

    async def _safe_reply_text_and_get_message(
        self,
        message: Message,
        text: str,
    ) -> Message | None:
        """Безопасная отправка текста с возвратом Message объекта.

        Используется когда нужно получить Message объект для дальнейшей работы
        (например, для получения message_id).

        Args:
            message: Сообщение для ответа.
            text: Текст для отправки.

        Returns:
            Message объект если сообщение отправлено успешно, None иначе.
        """
        try:

            async def _reply() -> Message:
                return await retry_on_connect_error(
                    message.reply_text,
                    text,
                    max_retries=MAX_RETRIES_DEFAULT,
                    delay=RETRY_DELAY_DEFAULT,
                )

            result = await self._rate_limiter.execute_with_rate_limit(_reply)
            return result
        except Exception as e:
            # retry_on_connect_error уже залогировал сетевые ошибки через log_event
            # Логируем только если это не сетевая ошибка (неожиданная ошибка)
            if self.services.error_classification_service is None:
                raise ValueError("error_classification_service must be provided in BotServices") from None
            if not self.services.error_classification_service.is_telegram_error(e):
                self.logger.warning(
                    f"Неожиданная ошибка при отправке сообщения: {e}",
                    exc_info=True,
                )
            return None

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
            if self.services.error_classification_service is None:
                raise ValueError("error_classification_service must be provided in BotServices") from None
            if self.services.error_classification_service.is_telegram_error(delete_error):
                # Сетевые ошибки Telegram API - логируем, но не прерываем
                self.logger.debug(
                    f"Не удалось удалить статусное сообщение (сетевая ошибка): {delete_error}",
                    exc_info=False,
                )
            else:
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

        Делегирует классификацию ошибок в ErrorClassificationService для соблюдения границ слоёв.

        Args:
            error: Исключение, которое произошло при отправке сообщения.
            context: Контекст для логирования (например, "отправке сообщения об ошибке").
        """
        if self.services.error_classification_service is None:
            raise ValueError("error_classification_service must be provided in BotServices")
        is_telegram_error = self.services.error_classification_service.is_telegram_error(error)
        if is_telegram_error:
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

            async def _reply() -> None:
                await retry_on_connect_error(
                    message.reply_text,
                    text,
                    max_retries=max_retries,
                    delay=delay,
                )

            await self._rate_limiter.execute_with_rate_limit(_reply)
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
        """Универсальный обработчик ошибок для команд.

        Делегирует всю бизнес-логику обработки ошибок в CommandErrorHandlerService.

        Args:
            update: Объект обновления Telegram.
            func: Асинхронная функция для выполнения команды.
            max_retries: Максимальное количество попыток для сетевых ошибок.
            timeout: Таймаут для выполнения команды в секундах.
        """

        async def send_error_message(text: str) -> None:
            """Вспомогательная функция для отправки сообщений об ошибках."""
            if update.message:
                await self._safe_reply_with_fallback(update.message, text)

        await self._command_error_handler.execute_with_error_handling(
            func=func,
            update=update,
            max_retries=max_retries,
            timeout=timeout,
            send_error_message=send_error_message,
        )

    async def _gather_with_timeout(
        self,
        *tasks: Awaitable,
        timeout: float | None = None,
        return_exceptions: bool = True,
    ) -> list:
        """Выполняет asyncio.gather с таймаутом для всех задач.

        Делегирует выполнение в shared.utils.async_utils.gather_with_timeout.

        Args:
            *tasks: Асинхронные задачи для параллельного выполнения.
            timeout: Таймаут для каждой задачи в секундах. Если None, используется
                CHAT_INFO_TIMEOUT_DEFAULT.
            return_exceptions: Если True, исключения возвращаются как результаты,
                а не пробрасываются.

        Returns:
            Список результатов выполнения задач. Если return_exceptions=True,
            исключения включаются в список как элементы.
        """
        return await gather_with_timeout(
            *tasks,
            timeout=timeout,
            return_exceptions=return_exceptions,
            default_timeout=CHAT_INFO_TIMEOUT_DEFAULT,
            logger=self.logger,
        )
