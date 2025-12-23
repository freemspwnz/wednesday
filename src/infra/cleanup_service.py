"""Service for graceful shutdown of async infrastructure resources used by workers.

Located in the infra layer because it operates purely on infrastructure concerns:
- ML clients (Kandinsky / GigaChat containers);
- Redis connection pool;
- PostgreSQL connection pool.

The goal is to encapsulate shutdown logic in one place and keep application
and domain layers free from infrastructure lifecycle details.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.protocols import ILogger


class CleanupService(BaseService):
    """Service that closes all async resources on worker shutdown.

    Errors during shutdown are logged but do not prevent the process from exiting.
    """

    def __init__(self, *, logger: ILogger) -> None:
        """Initialize cleanup service.

        Args:
            logger: Logger instance.
        """
        super().__init__(logger)

    async def cleanup_all(self) -> None:
        """Close all async resources.

        Closes:
        - ML clients (ImageClientContainer, TextClientContainer) via aclose()
        - Redis pool
        - PostgreSQL pool

        Errors are logged and swallowed to avoid blocking shutdown.
        """
        from infra.clients import get_image_client_container, get_text_client_container
        from infra.database.postgres_client import close_postgres_pool
        from infra.redis.redis_client import close_redis

        # Close ML clients
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

        # Close connection pools
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
