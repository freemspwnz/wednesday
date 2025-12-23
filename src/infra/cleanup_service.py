"""Сервис для graceful shutdown асинхронных инфраструктурных ресурсов воркеров.

Размещён в infra-слое, так как работает только с инфраструктурой:
- ML-клиенты (контейнеры Kandinsky / GigaChat);
- пул подключений Redis;
- пул подключений PostgreSQL.

Цель — инкапсулировать логику выключения инфраструктуры в одном месте и
не тянуть детали жизненного цикла процессов в application/domain-слои.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.protocols import ILogger


class CleanupService(BaseService):
    """Сервис, который закрывает все async-ресурсы при остановке worker'а.

    Ошибки при shutdown логируются, но не мешают завершению процесса.
    """

    def __init__(self, *, logger: ILogger) -> None:
        """Инициализирует сервис cleanup.

        Args:
            logger: Экземпляр логгера.
        """
        super().__init__(logger)

    async def cleanup_all(self) -> None:
        """Закрывает все async-ресурсы.

        Закрывает:
        - ML-клиенты (ImageClientContainer, TextClientContainer) через aclose()
        - пул Redis
        - пул PostgreSQL

        Ошибки логируются и игнорируются, чтобы не блокировать shutdown.
        """
        from infra.clients import get_image_client_container, get_text_client_container
        from infra.database.postgres_client import close_postgres_pool
        from infra.redis.redis_client import close_redis

        # Закрываем ML-клиенты
        try:
            image_container = get_image_client_container()
            await image_container.aclose()
            self.logger.info(
                "ImageClientContainer успешно закрыт",
                event="cleanup_ml_client_closed",
                status="success",
                client_type="image",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при закрытии ImageClientContainer: {e}",
                event="cleanup_ml_client_error",
                status="warning",
                client_type="image",
                error_type=type(e).__name__,
                error_message=str(e),
            )

        try:
            text_container = get_text_client_container()
            await text_container.aclose()
            self.logger.info(
                "TextClientContainer успешно закрыт",
                event="cleanup_ml_client_closed",
                status="success",
                client_type="text",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при закрытии TextClientContainer: {e}",
                event="cleanup_ml_client_error",
                status="warning",
                client_type="text",
                error_type=type(e).__name__,
                error_message=str(e),
            )

        # Закрываем пулы подключений
        try:
            await close_redis()
            self.logger.info(
                "Пул подключений Redis успешно закрыт",
                event="cleanup_redis_pool_closed",
                status="success",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при закрытии пула Redis: {e}",
                event="cleanup_redis_pool_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
            )

        try:
            await close_postgres_pool()
            self.logger.info(
                "Пул подключений PostgreSQL успешно закрыт",
                event="cleanup_postgres_pool_closed",
                status="success",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при закрытии пула PostgreSQL: {e}",
                event="cleanup_postgres_pool_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
            )
