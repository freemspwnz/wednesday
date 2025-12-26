"""Application service для очистки устаревших данных.

Координирует очистку различных типов данных:
- Старые записи dispatch_registry
- Временные файлы (если необходимо)
- Кэш (если необходимо)
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.protocols import IDispatchRegistry, ILogger


class DataCleanupService(BaseService):
    """Application service для очистки устаревших данных.

    Координирует очистку различных типов данных через репозитории.
    Соблюдает границы слоёв: application-слой использует протоколы, а не конкретные реализации.
    """

    def __init__(
        self,
        dispatch_registry: IDispatchRegistry,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис очистки данных.

        Args:
            dispatch_registry: Репозиторий для работы с dispatch_registry (через протокол).
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._dispatch_registry = dispatch_registry

    async def cleanup_all(self) -> None:
        """Выполняет очистку всех типов устаревших данных.

        Выполняет:
        - Очистку старых записей dispatch_registry
        - Другие операции очистки (если добавлены в будущем)

        Raises:
            Exception: При ошибке выполнения очистки.
        """
        # Очистка старых записей dispatch_registry
        await self._dispatch_registry.cleanup_old()

        self.logger.info(
            "Data cleanup completed successfully",
            event="data_cleanup_completed",
            status="success",
        )
