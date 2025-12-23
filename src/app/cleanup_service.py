"""Сервис для graceful shutdown ресурсов Celery worker."""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.protocols import ILogger


class CleanupService(BaseService):
    """Сервис для закрытия всех async ресурсов при остановке worker.

    Инкапсулирует логику cleanup для избежания зависимости от bot.services.cleanup()
    в инфраструктурном слое.
    """

    def __init__(self, *, logger: ILogger) -> None:
        """Инициализирует сервис cleanup.

        Args:
            logger: Экземпляр логгера.
        """
        super().__init__(logger)

    async def cleanup_all(self) -> None:
        """Закрывает все async ресурсы.

        Закрывает:
        - ML-клиенты (ImageClientContainer, TextClientContainer) через aclose()
        - Redis pool
        - PostgreSQL pool

        Ошибки при закрытии логируются, но не прерывают процесс shutdown.
        """
        from infra.clients import get_image_client_container, get_text_client_container
        from infra.database.postgres_client import close_postgres_pool
        from infra.redis.redis_client import close_redis

        # Закрываем ML-клиенты
        try:
            image_container = get_image_client_container()
            await image_container.aclose()
            self.logger.info("ImageClientContainer closed")
        except Exception as e:
            self.logger.warning(f"Error closing ImageClientContainer: {e}")

        try:
            text_container = get_text_client_container()
            await text_container.aclose()
            self.logger.info("TextClientContainer closed")
        except Exception as e:
            self.logger.warning(f"Error closing TextClientContainer: {e}")

        # Закрываем пулы подключений
        try:
            await close_redis()
            self.logger.info("Redis pool closed")
        except Exception as e:
            self.logger.warning(f"Error closing Redis pool: {e}")

        try:
            await close_postgres_pool()
            self.logger.info("PostgreSQL pool closed")
        except Exception as e:
            self.logger.warning(f"Error closing PostgreSQL pool: {e}")
