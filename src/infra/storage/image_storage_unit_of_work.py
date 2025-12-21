"""Unit of Work для управления сохранением изображений."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from shared.base.base_service import BaseService
from shared.protocols import ICache, IImageStorage, ILogger
from shared.retry import retry_standard


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

    Поддерживает отложенное пересоздание кэша при временных ошибках:
    - При ошибке сохранения в кэш (но успешном сохранении в хранилище) операция
      автоматически добавляется в очередь пересоздания
    - Фоновая задача через asyncio.create_task пересоздаёт кэш из хранилища
    - Используется exponential retry механизм для обработки временных ошибок
    - Кэш пересоздаётся даже при временных сбоях (пул исчерпан, таймауты)
    """

    def __init__(
        self,
        cache: ICache[tuple[bytes, str]] | None = None,
        storage: IImageStorage | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует Unit of Work.

        Args:
            cache: Сервис кэширования (опционально).
            storage: Сервис файлового хранилища (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._cache = cache
        self._storage = storage
        self._operations: list[ImageSaveOperation] = []
        self._failed_cache_operations: deque[ImageSaveOperation] = deque()
        self._rebuild_task: asyncio.Task | None = None
        self._rebuild_running: bool = False

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
        4. При ошибке кэша после успешного сохранения в хранилище:
           - Логирует предупреждение
           - Считает операцию успешной (хранилище имеет приоритет)
           - Автоматически добавляет операцию в очередь пересоздания кэша
           - Запускает фоновую задачу для пересоздания кэша из хранилища

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
                self.logger.debug(
                    f"Изображение сохранено в хранилище: {storage_path}",
                    event="image_storage_saved",
                    status="saved",
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
                self.logger.debug(
                    f"Изображение сохранено в кэш: {cache_key}",
                    event="image_cache_saved",
                    status="cached",
                )
            except Exception as e:
                self.logger.warning(f"Ошибка при сохранении в кэш: {e}")
                # Если кэш не удался, но хранилище успешно - это приемлемо
                # Кэш может быть пересоздан позже
                if storage_success:
                    self.logger.info(
                        "Изображение сохранено в хранилище, но не в кэш. Это приемлемо, кэш может быть пересоздан.",
                    )
                    # Добавляем в очередь для пересоздания
                    self._failed_cache_operations.append(operation)
                    self.logger.info(
                        f"Операция добавлена в очередь пересоздания кэша: "
                        f"cache_key={operation.cache_key}, storage_path={operation.storage_path}",
                    )
                    # Запускаем фоновую задачу, если она ещё не запущена
                    if not self._rebuild_running:
                        self._start_background_rebuild_task()

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

    @retry_standard(
        service_name="cache_rebuild",
        method_name="rebuild_cache_from_storage",
    )
    async def rebuild_cache_from_storage(
        self,
        cache_key: str,
        storage_path: str,
        caption: str,
    ) -> bool:
        """Пересоздаёт кэш из файла в хранилище.

        Использует exponential retry для обработки временных ошибок.
        Используется, когда сохранение в хранилище успешно,
        но сохранение в кэш не удалось.

        Args:
            cache_key: Ключ для кэша (prompt).
            storage_path: Путь к файлу в хранилище.
            caption: Подпись к изображению.

        Returns:
            True если кэш успешно пересоздан, False иначе.

        Raises:
            CacheError: При ошибках доступа к кэшу.
            StorageError: При ошибках чтения из хранилища.
        """
        if not self._cache or not self._storage:
            return False

        try:
            # Загружаем изображение из хранилища
            image_data = await self._storage.get_by_path(storage_path)

            # Сохраняем в кэш
            await self._cache.set(cache_key, (image_data, caption))

            self.logger.info(
                f"Кэш пересоздан из хранилища: cache_key={cache_key}, storage_path={storage_path}",
            )
            return True
        except Exception as e:
            self.logger.warning(
                f"Не удалось пересоздать кэш из хранилища: {e}",
            )
            raise  # Пробрасываем для retry механизма

    def _start_background_rebuild_task(self) -> None:
        """Запускает фоновую задачу для пересоздания кэша."""
        if self._rebuild_task is None or self._rebuild_task.done():
            self._rebuild_running = True
            self._rebuild_task = asyncio.create_task(
                self._rebuild_failed_caches_loop(),
            )
            self.logger.info("Запущена фоновая задача пересоздания кэша")

    async def _rebuild_failed_caches_loop(self) -> None:
        """Цикл пересоздания кэша для неудачных операций."""
        while self._failed_cache_operations:
            operation = self._failed_cache_operations.popleft()
            try:
                if not operation.storage_path:
                    self.logger.warning(
                        f"Пропущена операция без storage_path: cache_key={operation.cache_key}",
                    )
                    continue

                success = await self.rebuild_cache_from_storage(
                    cache_key=operation.cache_key,
                    storage_path=operation.storage_path,
                    caption=operation.caption,
                )
                if success:
                    self.logger.info(
                        f"Кэш успешно пересоздан: cache_key={operation.cache_key}",
                    )
                else:
                    # Если не удалось, добавляем обратно в очередь
                    self._failed_cache_operations.append(operation)
            except Exception as e:
                self.logger.error(
                    f"Ошибка при пересоздании кэша для {operation.cache_key}: {e}",
                    exc_info=True,
                )
                # Добавляем обратно в очередь для повторной попытки
                self._failed_cache_operations.append(operation)

            # Небольшая задержка между операциями
            await asyncio.sleep(1.0)

        self._rebuild_running = False
        self.logger.info("Фоновая задача пересоздания кэша завершена")
