"""Сервис для graceful shutdown асинхронных инфраструктурных ресурсов воркеров.

Размещён в infra-слое, так как работает только с инфраструктурой:
- ML-клиенты (контейнеры Kandinsky / GigaChat);
- пул подключений Redis;
- пул подключений PostgreSQL.

Цель — инкапсулировать логику выключения инфраструктуры в одном месте и
не тянуть детали жизненного цикла процессов в application/domain-слои.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from shared.base.base_service import BaseService
from shared.protocols import ILogger

if TYPE_CHECKING:
    from infra.clients.image_client_container import ImageClientContainer
    from infra.clients.text_client_container import TextClientContainer
    from infra.database.postgres_client import PostgresPoolFactory
    from infra.redis.redis_client import RedisClientFactory


class AsyncClosable(Protocol):
    """Protocol для ресурсов, которые можно закрыть асинхронно через aclose()."""

    async def aclose(self) -> None:
        """Закрывает ресурс асинхронно."""
        ...


class AsyncCloseable(Protocol):
    """Protocol для ресурсов, которые можно закрыть асинхронно через close()."""

    async def close(self) -> None:
        """Закрывает ресурс асинхронно."""
        ...


class SyncClosable(Protocol):
    """Protocol для ресурсов, которые можно закрыть синхронно."""

    def close(self) -> None:
        """Закрывает ресурс синхронно."""
        ...


ClosableResource = AsyncClosable | AsyncCloseable | SyncClosable


class CleanupService(BaseService):
    def __init__(
        self,
        *,
        logger: ILogger,
        pool_factory: PostgresPoolFactory | None = None,
        redis_factory: RedisClientFactory | None = None,
        image_container: ImageClientContainer | None = None,
        text_container: TextClientContainer | None = None,
    ) -> None:
        super().__init__(logger)
        self._pool_factory = pool_factory
        self._redis_factory = redis_factory
        self._image_container = image_container
        self._text_container = text_container

    async def _safe_close(self, resource: ClosableResource | None, name: str) -> None:
        """Вспомогательный метод для безопасного закрытия одного ресурса."""
        if resource is None:
            return

        try:
            # Проверяем наличие метода aclose или close
            if hasattr(resource, "aclose"):
                aclose_method = resource.aclose
                if asyncio.iscoroutinefunction(aclose_method):
                    await aclose_method()
                else:
                    # Fallback для синхронного aclose (не должно происходить, но на всякий случай)
                    result = aclose_method()
                    if asyncio.iscoroutine(result):
                        await result
            elif hasattr(resource, "close"):
                close_method = resource.close
                if asyncio.iscoroutinefunction(close_method):
                    await close_method()
                else:
                    # Синхронный close
                    close_method()

            self.logger.info(f"Ресурс {name} успешно закрыт", event="cleanup_resource_closed", resource=name)
        except Exception as e:
            self.logger.warning(
                f"Ошибка при закрытии {name}: {e}", event="cleanup_resource_error", resource=name, error=str(e)
            )

    async def cleanup_all(self) -> None:
        """Закрывает все ресурсы параллельно с общим таймаутом."""
        self.logger.info("Запуск полного cleanup ресурсов воркера...")

        tasks = [
            self._safe_close(self._image_container, "ImageClientContainer"),
            self._safe_close(self._text_container, "TextClientContainer"),
            self._safe_close(self._redis_factory, "RedisPool"),
            self._safe_close(self._pool_factory, "PostgresPool"),
        ]

        try:
            # Ограничиваем всё время закрытия (например, 5 секунд)
            # Чтобы воркер не завис при выключении
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)
        except TimeoutError:
            self.logger.error("Превышен таймаут при cleanup ресурсов!")
        except Exception as e:
            self.logger.error(f"Критическая ошибка во время cleanup: {e}")
