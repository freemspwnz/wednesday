"""Unit of Work для управления сохранением изображений."""

from __future__ import annotations

from dataclasses import dataclass

from services.base.base_service import BaseService
from services.protocols import ICache, IImageStorage


@dataclass
class ImageSaveOperation:
    """Операция сохранения изображения."""

    image_data: bytes
    caption: str
    cache_key: str
    storage_prefix: str = "frog"

    # Результаты выполнения операций
    cache_saved: bool = False
    storage_path: str | None = None
    storage_saved: bool = False


class ImageStorageUnitOfWork(BaseService):
    """Unit of Work для управления сохранением изображений в кэш и хранилище.

    Группирует операции сохранения изображения и обеспечивает компенсационные
    действия при ошибках для улучшения согласованности данных.
    """

    def __init__(
        self,
        cache: ICache[tuple[bytes, str]] | None = None,
        storage: IImageStorage | None = None,
    ) -> None:
        """Инициализирует Unit of Work.

        Args:
            cache: Сервис кэширования (опционально).
            storage: Сервис файлового хранилища (опционально).
        """
        super().__init__()
        self._cache = cache
        self._storage = storage
        self._operations: list[ImageSaveOperation] = []

    async def save_image(
        self,
        image_data: bytes,
        caption: str,
        cache_key: str,
        storage_prefix: str = "frog",
    ) -> bool:
        """Сохраняет изображение в кэш и хранилище.

        Выполняет сохранение с компенсационными действиями при ошибках:
        1. Сначала сохраняет в хранилище (более критичное)
        2. Затем сохраняет в кэш
        3. При ошибке хранилища - не сохраняет в кэш
        4. При ошибке кэша после успешного сохранения в хранилище - логирует, но считает операцию успешной

        Args:
            image_data: Байты изображения.
            caption: Подпись к изображению.
            cache_key: Ключ для кэша.
            storage_prefix: Префикс для файлового хранилища.

        Returns:
            True если сохранение успешно (хотя бы в одно хранилище), False иначе.
        """
        operation = ImageSaveOperation(
            image_data=image_data,
            caption=caption,
            cache_key=cache_key,
            storage_prefix=storage_prefix,
        )
        self._operations.append(operation)

        # Стратегия: сначала хранилище (более критичное), потом кэш
        storage_success = False
        cache_success = False

        # 1. Сохранение в хранилище (приоритетное)
        if self._storage:
            try:
                storage_path = await self._storage.save(
                    image_data,
                    prefix=storage_prefix,
                )
                operation.storage_path = storage_path
                operation.storage_saved = True
                storage_success = True
                self.log_event(
                    event="image_storage_saved",
                    status="saved",
                    level="debug",
                    message=f"Изображение сохранено в хранилище: {storage_path}",
                )
            except Exception as e:
                self.logger.warning(f"Ошибка при сохранении в хранилище: {e}")
                # Если хранилище не удалось, не сохраняем в кэш (компенсация)
                return False

        # 2. Сохранение в кэш (второстепенное)
        if self._cache:
            try:
                await self._cache.set(cache_key, (image_data, caption))
                operation.cache_saved = True
                cache_success = True
                self.log_event(
                    event="image_cache_saved",
                    status="cached",
                    level="debug",
                    message=f"Изображение сохранено в кэш: {cache_key}",
                )
            except Exception as e:
                self.logger.warning(f"Ошибка при сохранении в кэш: {e}")
                # Если кэш не удался, но хранилище успешно - это приемлемо
                # Кэш может быть пересоздан позже
                if storage_success:
                    self.logger.info(
                        "Изображение сохранено в хранилище, но не в кэш. Это приемлемо, кэш может быть пересоздан.",
                    )

        # Операция считается успешной, если сохранено хотя бы в одно хранилище
        return storage_success or cache_success

    async def commit(self) -> bool:
        """Фиксирует все операции Unit of Work.

        В текущей реализации операции выполняются сразу при добавлении,
        но метод оставлен для совместимости с паттерном Unit of Work.

        Returns:
            True если все операции успешны, False иначе.
        """
        # В текущей реализации операции выполняются сразу
        # Этот метод можно расширить для батчинга операций в будущем
        return all(op.storage_saved or op.cache_saved for op in self._operations)

    async def rollback(self) -> None:
        """Откатывает операции Unit of Work.

        Выполняет компенсационные действия для отката операций:
        - Удаляет из кэша, если было сохранено
        - Удаляет из хранилища (если поддерживается)

        Примечание: полный откат может быть невозможен для файлового хранилища.
        """
        for operation in reversed(self._operations):
            # Компенсация: удаляем из кэша
            if operation.cache_saved and self._cache:
                try:
                    await self._cache.delete(operation.cache_key)
                    self.logger.debug(f"Откат: удалено из кэша {operation.cache_key}")
                except Exception as e:
                    self.logger.warning(f"Ошибка при откате кэша {operation.cache_key}: {e}")

            # Компенсация: удаляем из хранилища (если поддерживается)
            # Примечание: мы не удаляем файлы из хранилища при ошибках сохранения кэша,
            # так как хранилище имеет приоритет над кэшем
            if operation.storage_saved and operation.storage_path and self._storage:
                self.logger.debug(
                    f"Откат: файл в хранилище не удалён (хранилище имеет приоритет): {operation.storage_path}",
                )

        self._operations.clear()

    def clear(self) -> None:
        """Очищает список операций без выполнения компенсационных действий."""
        self._operations.clear()
