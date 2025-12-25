"""Application service для координации сохранения изображений.

Координирует работу:
- IImageStorageUnitOfWork (сохранение в кэш и хранилище)
- IMetrics (метрики сохранения)
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.base.exceptions import ServiceError, StorageError
from shared.protocols import IImageStorageUnitOfWork, ILogger, IMetrics


class ImageStorageCoordinator(BaseService):
    """Координатор сохранения изображений.

    Отвечает за:
    - Сохранение изображений через Unit of Work
    - Обработку ошибок сохранения и rollback
    - Запись метрик сохранения (опционально)
    """

    def __init__(
        self,
        storage_unit_of_work: IImageStorageUnitOfWork,
        metrics: IMetrics | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует координатор сохранения.

        Args:
            storage_unit_of_work: Unit of Work для сохранения изображений (обязательно).
            metrics: Сервис записи метрик (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._storage_uow = storage_unit_of_work
        self._metrics = metrics

    async def save_image(
        self,
        image_data: bytes,
        caption: str,
        cache_key: str,
        storage_prefix: str = "frog",
        user_id_str: str | None = None,
    ) -> bool:
        """Сохраняет изображение через Unit of Work.

        Args:
            image_data: Байты изображения.
            caption: Подпись к изображению.
            cache_key: Ключ для кэша (обычно промпт).
            storage_prefix: Префикс для файлового хранилища.
            user_id_str: Идентификатор пользователя для логирования.

        Returns:
            True если сохранение успешно (хотя бы в одно хранилище), False иначе.
        """
        try:
            success = await self._storage_uow.save_image(
                image_data=image_data,
                caption=caption,
                cache_key=cache_key,
                storage_prefix=storage_prefix,
            )
            if success:
                self.logger.info(
                    "Изображение сохранено в хранилища",
                    event="image_saved",
                    user_id=user_id_str,
                    status="saved",
                )
                # Метрики сохранения можно добавить здесь, если нужно
                # await self._record_metrics("storage_success", user_id_str)
            else:
                self.logger.warning(
                    "Не удалось сохранить изображение ни в одно хранилище",
                    event="image_save_failed",
                    user_id=user_id_str,
                    status="warning",
                )
            return success
        except StorageError as e:
            self.logger.error(
                f"Критическая ошибка при сохранении изображения: {e}",
                event="storage_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                user_id=user_id_str,
                exc_info=True,
            )
            # Пытаемся откатить
            try:
                await self._storage_uow.rollback()
            except StorageError as rollback_error:
                self.logger.error(
                    f"Ошибка при откате сохранения: {rollback_error}",
                    event="storage_rollback_error",
                    status="error",
                    error_type=type(rollback_error).__name__,
                    error_message=str(rollback_error),
                    user_id=user_id_str,
                    exc_info=True,
                )
            return False

    async def _record_metrics(
        self,
        operation: str,
        user_id_str: str | None,
    ) -> None:
        """Записывает метрики для операции сохранения.

        Args:
            operation: Тип операции ('storage_success', 'storage_failed').
            user_id_str: Идентификатор пользователя для логирования.
        """
        if self._metrics is None:
            return

        try:
            # Метрики сохранения можно добавить в IMetrics, если нужно
            # if operation == "storage_success":
            #     await self._metrics.increment_storage_success()
            # elif operation == "storage_failed":
            #     await self._metrics.increment_storage_failed()
            pass
        except ServiceError as e:
            self.logger.warning(
                f"Ошибка при записи метрики {operation}: {e}",
                event="metrics_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
                user_id=user_id_str,
            )
