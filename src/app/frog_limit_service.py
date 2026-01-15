"""Application service для rate limiting команды /frog.

Инкапсулирует логику проверки глобального и per-user лимитов для команды /frog,
используя инфраструктурный RateLimiter.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.config import AppSettings
from shared.protocols.infrastructure import ILogger, IRateLimiter
from shared.protocols.repositories import IUsageTracker

# Константы
SECONDS_PER_MINUTE = 60  # секунд в минуте


class FrogRateLimiterService(BaseService):
    """Application service для проверки rate limit команды /frog.

    Проверяет два уровня лимитов:
    - Глобальный лимит: максимум запросов за временное окно (для всех пользователей)
    - Per-user лимит: минимальный интервал между запросами одного пользователя

    Администраторы пропускают per-user лимит, но подчиняются глобальному лимиту.
    """

    def __init__(
        self,
        *,
        settings: AppSettings,
        global_limiter: IRateLimiter,
        user_limiter: IRateLimiter,
        logger: ILogger,
        usage: IUsageTracker | None = None,
    ) -> None:
        """Инициализирует сервис rate limiting для команды /frog.

        Args:
            settings: Настройки приложения с параметрами rate limit.
            global_limiter: Лимитер для глобального лимита запросов.
            user_limiter: Лимитер для per-user лимита запросов.
            logger: Экземпляр логгера для использования в сервисе.
            usage: Трекер использования для проверки месячных лимитов (опционально).
        """
        super().__init__(logger)
        self._settings = settings
        self._global_limiter = global_limiter
        self._user_limiter = user_limiter
        self._usage = usage

    async def check_and_consume(
        self,
        user_id: int,
        is_admin: bool,
    ) -> tuple[bool, str | None]:
        """Проверяет rate limit и потребляет квоту, если разрешено.

        Проверяет сначала глобальный лимит, затем per-user лимит (для не-админов).
        Если любой из лимитов превышен, возвращает False с сообщением для пользователя.

        Args:
            user_id: ID пользователя для проверки per-user лимита.
            is_admin: Флаг, является ли пользователь администратором.
                Администраторы пропускают per-user лимит.

        Returns:
            Кортеж (is_allowed, user_message):
            - is_allowed: True если запрос разрешён, False если заблокирован.
            - user_message: Сообщение для пользователя (None если разрешено,
                текст сообщения об ошибке если заблокировано).
        """
        # Проверка глобального лимита
        if not await self._global_limiter.is_allowed("global"):
            self.logger.warning(
                f"Глобальный rate limit /frog превышен: {self._settings.frog_rate_limit_max_requests} "
                f"запросов за {self._settings.frog_rate_limit_window_seconds}с",
            )
            return (
                False,
                "🚦 Слишком много запросов! Попробуйте через минуту.",
            )

        # Проверка per-user лимита (пропускаем для админов)
        if not is_admin:
            user_key = str(user_id)
            if not await self._user_limiter.is_allowed(user_key):
                remaining_seconds = self._settings.frog_rate_limit_minutes * SECONDS_PER_MINUTE
                self.logger.info(f"Rate limit для пользователя {user_id}: {remaining_seconds}с осталось")
                return (
                    False,
                    f"⏰ Повторная генерация доступна через {remaining_seconds}с",
                )

        # Все проверки пройдены
        return (True, None)

    async def check_generation_allowed(self) -> tuple[bool, str | None]:
        """Проверяет, разрешена ли генерация с учетом месячного лимита.

        Проверяет месячный лимит генераций через IUsageTracker.
        Используется для команд, которые не требуют rate limiting (например, /force_send).

        Returns:
            Кортеж (is_allowed, error_message):
            - is_allowed: True если генерация разрешена, False если лимит исчерпан.
            - error_message: Сообщение об ошибке (None если разрешено,
                текст сообщения если лимит исчерпан).
        """
        if self._usage is None:
            # Если usage tracker не доступен, разрешаем генерацию
            return (True, None)

        can_generate = await self._usage.can_use_frog()
        if not can_generate:
            total, threshold, quota = await self._usage.get_limits_info()
            error_message = (
                f"🚫 Лимит ручных генераций исчерпан: {total}/{quota}. Доступ к /frog закрыт после {threshold}."
            )
            self.logger.info(
                f"Лимит ручных генераций исчерпан: {total}/{quota}, порог: {threshold}",
            )
            return (False, error_message)

        return (True, None)
