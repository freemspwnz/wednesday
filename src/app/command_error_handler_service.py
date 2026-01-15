"""Application service для обработки ошибок выполнения команд.

Инкапсулирует всю бизнес-логику обработки ошибок: классификацию типов ошибок,
решение о retry, управление таймаутами, форматирование сообщений об ошибках.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.base.exceptions import RepoError, ServiceError
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.error import NetworkError, TelegramError, TimedOut

    from app.error_message_formatter_service import ErrorMessageFormatterService
    from app.retry_strategy_service import RetryStrategyService


class CommandErrorHandlerService(BaseService):
    """Сервис для обработки ошибок выполнения команд.

    Инкапсулирует всю бизнес-логику обработки ошибок: классификацию типов ошибок,
    решение о retry, управление таймаутами, форматирование сообщений об ошибках.
    """

    def __init__(
        self,
        error_formatter: ErrorMessageFormatterService,
        retry_strategy: RetryStrategyService,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис обработки ошибок.

        Args:
            error_formatter: Сервис для форматирования сообщений об ошибках.
            retry_strategy: Сервис для расчета стратегии retry.
            logger: Логгер для логирования операций.
        """
        super().__init__(logger)
        self._error_formatter = error_formatter
        self._retry_strategy = retry_strategy

    async def execute_with_error_handling(
        self,
        func: Callable[[], Awaitable[None]],
        update: Update,
        max_retries: int = 1,
        timeout: float | None = None,
        send_error_message: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """Выполняет команду с обработкой ошибок.

        Args:
            func: Асинхронная функция для выполнения команды.
            update: Объект обновления Telegram.
            max_retries: Максимальное количество попыток для сетевых ошибок.
            timeout: Таймаут для выполнения команды в секундах.
            send_error_message: Функция для отправки сообщения об ошибке пользователю.
        """
        max_retries = self._retry_strategy.normalize_max_retries(max_retries)

        async def _execute_with_retries() -> None:
            """Внутренняя функция для выполнения команды с retry-логикой."""
            attempt = 0

            while attempt < max_retries:
                try:
                    await func()
                    return
                except (ValueError, TypeError, AttributeError) as e:
                    await self._handle_validation_error(e, update, send_error_message)
                    return
                except (TelegramError, NetworkError, TimedOut) as e:
                    attempt += 1
                    should_retry = await self._handle_network_error_with_retry(
                        e, update, attempt, max_retries, send_error_message
                    )
                    if should_retry:
                        continue
                    return
                except ServiceError as e:
                    await self._handle_service_error(e, update, send_error_message)
                    return
                except RepoError as e:
                    await self._handle_repo_error(e, update, send_error_message)
                    return
                except asyncio.CancelledError:
                    self.logger.info("Команда была отменена")
                    raise

        if timeout is not None:
            try:
                await asyncio.wait_for(_execute_with_retries(), timeout=timeout)
            except TimeoutError:
                self.logger.error(
                    f"Команда не завершилась за {timeout}с, прерываем выполнение",
                    exc_info=False,
                )
                if send_error_message and update.message:
                    error_message = self._error_formatter.format_timeout_error()
                    await send_error_message(error_message)
            except asyncio.CancelledError:
                raise
        else:
            await _execute_with_retries()

    async def _handle_validation_error(
        self,
        error: ValueError | TypeError | AttributeError,
        update: Update,
        send_error_message: Callable[[str], Awaitable[None]] | None,
    ) -> None:
        """Обрабатывает ошибки валидации данных."""
        self.logger.error(f"Ошибка валидации: {error}", exc_info=True)
        if send_error_message and update.message:
            error_message = self._error_formatter.format_validation_error()
            await send_error_message(error_message)

    async def _handle_network_error_with_retry(
        self,
        error: TelegramError | NetworkError | TimedOut,
        update: Update,
        attempt: int,
        max_retries: int,
        send_error_message: Callable[[str], Awaitable[None]] | None,
    ) -> bool:
        """Обрабатывает сетевые ошибки Telegram API с retry-логикой."""
        if attempt < max_retries:
            wait_time = self._retry_strategy.calculate_wait_time(attempt)
            self.logger.warning(
                f"Сетевая ошибка Telegram API (попытка {attempt}/{max_retries}): {error}. Повтор через {wait_time}с",
            )
            await asyncio.sleep(wait_time)
            return True

        self.logger.warning(f"Сетевая ошибка Telegram API после {max_retries} попыток: {error}")
        if send_error_message and update.message:
            error_message = self._error_formatter.format_network_error()
            await send_error_message(error_message)
        return False

    async def _handle_service_error(
        self,
        error: ServiceError,
        update: Update,
        send_error_message: Callable[[str], Awaitable[None]] | None,
    ) -> None:
        """Обрабатывает ошибки сервисного слоя."""
        self.logger.error(f"Ошибка сервиса: {error}", exc_info=True)
        if send_error_message and update.message:
            error_message = self._error_formatter.format_service_error(error)
            await send_error_message(error_message)

    async def _handle_repo_error(
        self,
        error: RepoError,
        update: Update,
        send_error_message: Callable[[str], Awaitable[None]] | None,
    ) -> None:
        """Обрабатывает ошибки репозитория."""
        self.logger.error(f"Ошибка репозитория: {error}", exc_info=True)
        if send_error_message and update.message:
            error_message = self._error_formatter.format_repo_error(error)
            await send_error_message(error_message)
