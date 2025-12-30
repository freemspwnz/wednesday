"""Unit of Work для управления сохранением изображений."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.image_existence_service import ImageExistenceService
from infra.storage.failed_cache_queue import FailedCacheOperation, FailedCacheQueue
from shared.base.base_service import BaseService
from shared.protocols import IImageStorage, ILogger
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
    """Unit of Work для управления сохранением изображений в хранилище.

    Группирует операции сохранения изображения и обеспечивает компенсационные
    действия при ошибках для улучшения согласованности данных.

    Поддерживает отложенное сохранение в постоянное хранилище при временных ошибках:
    - При ошибке сохранения в постоянное хранилище (но успешном сохранении в файловое хранилище)
      операция автоматически добавляется в очередь пересоздания
    - Фоновая задача через asyncio.create_task пересоздаёт запись в постоянном хранилище
    - Используется exponential retry механизм для обработки временных ошибок
    """

    def __init__(
        self,
        failed_cache_queue: FailedCacheQueue,
        image_existence_service: ImageExistenceService | None = None,
        storage: IImageStorage | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует Unit of Work.

        Args:
            failed_cache_queue: Очередь для персистентного хранения операций
                пересоздания (обязательно). Использует Redis с автоматическим
                fallback на in-memory при недоступности Redis.
            image_existence_service: Сервис проверки существования изображений (опционально).
                Используется для сохранения в постоянное хранилище (PostgreSQL + FS).
            storage: Сервис файлового хранилища (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._existence_service = image_existence_service
        self._storage = storage
        self._operations: list[ImageSaveOperation] = []
        self._failed_cache_queue = failed_cache_queue
        self._rebuild_task: asyncio.Task | None = None
        self._rebuild_running: bool = False

    async def save_image(
        self,
        image_data: bytes,
        caption: str,
        cache_key: str,
        storage_prefix: str = "frog",
    ) -> bool:
        """Сохраняет изображение в постоянное хранилище и файловое хранилище.

        Выполняет сохранение с компенсационными действиями при ошибках:
        1. Сначала сохраняет в файловое хранилище (более критичное)
        2. Затем сохраняет в постоянное хранилище (PostgreSQL + FS через ImageExistenceService)
        3. При ошибке файлового хранилища - не сохраняет в постоянное хранилище
        4. При ошибке постоянного хранилища после успешного сохранения в файловое:
           - Логирует предупреждение
           - Считает операцию успешной (файловое хранилище имеет приоритет)
           - Автоматически добавляет операцию в очередь пересоздания
           - Запускает фоновую задачу для пересоздания записи из файлового хранилища

        Args:
            image_data: Байты изображения.
            caption: Подпись к изображению.
            cache_key: Промпт для сохранения (используется как ключ).
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

        # Стратегия: сначала файловое хранилище (более критичное), потом постоянное
        storage_success = False
        persistent_success = False

        # 1. Сохранение в файловое хранилище (приоритетное)
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
                    f"Изображение сохранено в файловое хранилище: {storage_path}",
                    event="image_storage_saved",
                    status="saved",
                )
            except Exception as e:
                self.logger.warning(f"Ошибка при сохранении в файловое хранилище: {e}")
                # Если файловое хранилище не удалось, не сохраняем в постоянное (компенсация)
                return False

        # 2. Сохранение в постоянное хранилище (PostgreSQL + FS)
        if self._existence_service:
            try:
                await self._existence_service.save_image_by_prompt(
                    prompt=cache_key,
                    image_data=image_data,
                )
                operation.cache_saved = True  # Используем старое поле для совместимости
                persistent_success = True
                self.logger.debug(
                    f"Изображение сохранено в постоянное хранилище: prompt={cache_key}",
                    event="image_persistent_saved",
                    status="saved",
                )
            except Exception as e:
                self.logger.warning(f"Ошибка при сохранении в постоянное хранилище: {e}")
                # Если постоянное хранилище не удалось, но файловое успешно - это приемлемо
                # Постоянное хранилище может быть пересоздано позже
                if storage_success:
                    self.logger.info(
                        "Изображение сохранено в файловое хранилище, но не в постоянное. "
                        "Это приемлемо, запись может быть пересоздана.",
                        event="persistent_save_failed_storage_ok",
                        status="warning",
                        cache_key=operation.cache_key,
                        storage_path=operation.storage_path,
                    )

                    # Добавляем в Redis очередь
                    if operation.storage_path:
                        await self._failed_cache_queue.enqueue(
                            FailedCacheOperation(
                                cache_key=operation.cache_key,
                                storage_path=operation.storage_path,
                                caption=operation.caption,
                            )
                        )
                        self.logger.info(
                            "Операция добавлена в очередь пересоздания",
                            event="failed_cache_enqueued",
                            status="success",
                            cache_key=operation.cache_key,
                        )

                    # Запускаем фоновую задачу, если она ещё не запущена
                    if not self._rebuild_running:
                        self._start_background_rebuild_task()

        # Операция считается успешной, если сохранено хотя бы в одно хранилище
        return storage_success or persistent_success

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
            # Компенсация: удаление из постоянного хранилища не поддерживается
            # (файлы в PostgreSQL + FS не удаляются при откате)
            if operation.cache_saved:
                self.logger.debug(
                    f"Откат: запись в постоянном хранилище не удалена "
                    f"(удаление не поддерживается): {operation.cache_key}",
                )

            # Компенсация: удаляем из файлового хранилища (если поддерживается)
            # Примечание: мы не удаляем файлы из хранилища при ошибках сохранения в постоянное,
            # так как файловое хранилище имеет приоритет
            if operation.storage_saved and operation.storage_path and self._storage:
                self.logger.debug(
                    f"Откат: файл в хранилище не удалён (хранилище имеет приоритет): {operation.storage_path}",
                )

        self._operations.clear()

    def clear(self) -> None:
        """Очищает список операций без выполнения компенсационных действий."""
        self._operations.clear()

    @retry_standard(
        service_name="persistent_rebuild",
        method_name="rebuild_persistent_from_storage",
    )
    async def rebuild_persistent_from_storage(
        self,
        cache_key: str,
        storage_path: str,
        caption: str,
    ) -> bool:
        """Пересоздаёт запись в постоянном хранилище из файла в файловом хранилище.

        Использует exponential retry для обработки временных ошибок.
        Используется, когда сохранение в файловое хранилище успешно,
        но сохранение в постоянное хранилище не удалось.

        Args:
            cache_key: Промпт для сохранения.
            storage_path: Путь к файлу в файловом хранилище.
            caption: Подпись к изображению.

        Returns:
            True если запись успешно пересоздана, False иначе.

        Raises:
            CacheError: При ошибках доступа к постоянному хранилищу.
            StorageError: При ошибках чтения из файлового хранилища.
        """
        if not self._existence_service or not self._storage:
            return False

        try:
            # Загружаем изображение из файлового хранилища
            image_data = await self._storage.get_by_path(storage_path)

            # Сохраняем в постоянное хранилище
            await self._existence_service.save_image_by_prompt(
                prompt=cache_key,
                image_data=image_data,
            )

            self.logger.info(
                f"Запись в постоянном хранилище пересоздана из файлового: "
                f"prompt={cache_key}, storage_path={storage_path}",
            )
            return True
        except Exception as e:
            self.logger.warning(
                f"Не удалось пересоздать запись в постоянном хранилище: {e}",
            )
            raise  # Пробрасываем для retry механизма

    def _start_background_rebuild_task(self) -> None:
        """Запускает фоновую задачу для пересоздания записей в постоянном хранилище."""
        if self._rebuild_task is None or self._rebuild_task.done():
            self._rebuild_running = True
            self._rebuild_task = asyncio.create_task(
                self._rebuild_failed_caches_loop(),
            )
            self.logger.info("Запущена фоновая задача пересоздания записей в постоянном хранилище")

    async def _rebuild_failed_caches_loop(self) -> None:
        """Цикл пересоздания записей в постоянном хранилище для неудачных операций из Redis очереди."""
        consecutive_empty = 0
        max_consecutive_empty = 5  # Останавливаемся после 5 пустых проверок

        while consecutive_empty < max_consecutive_empty:
            failed_op = await self._failed_cache_queue.dequeue()
            if failed_op is None:
                consecutive_empty += 1
                if consecutive_empty < max_consecutive_empty:
                    await asyncio.sleep(1.0)
                continue

            consecutive_empty = 0  # Сброс счётчика при успешном извлечении

            try:
                if not failed_op.storage_path:
                    self.logger.warning(
                        "Пропущена операция без storage_path из очереди",
                        event="rebuild_cache_skipped",
                        status="warning",
                        cache_key=failed_op.cache_key,
                    )
                    continue

                success = await self.rebuild_persistent_from_storage(
                    cache_key=failed_op.cache_key,
                    storage_path=failed_op.storage_path,
                    caption=failed_op.caption,
                )
                if success:
                    self.logger.info(
                        "Запись в постоянном хранилище успешно пересоздана из очереди",
                        event="persistent_rebuild_success",
                        status="success",
                        cache_key=failed_op.cache_key,
                    )
                else:
                    # Возвращаем обратно в очередь для повторной попытки
                    await self._failed_cache_queue.enqueue(failed_op)
                    self.logger.warning(
                        "Операция возвращена в очередь после неудачи",
                        event="persistent_rebuild_requeue",
                        status="warning",
                        cache_key=failed_op.cache_key,
                    )
            except Exception as e:
                self.logger.error(
                    f"Ошибка при пересоздании записи в постоянном хранилище для {failed_op.cache_key}: {e}",
                    event="persistent_rebuild_error",
                    status="error",
                    cache_key=failed_op.cache_key,
                    exc_info=True,
                )
                # Возвращаем обратно в очередь для повторной попытки
                try:
                    await self._failed_cache_queue.enqueue(failed_op)
                except Exception as enqueue_error:
                    self.logger.error(
                        f"Критическая ошибка: не удалось вернуть операцию в очередь: {enqueue_error}",
                        event="cache_rebuild_requeue_error",
                        status="critical",
                        cache_key=failed_op.cache_key,
                        exc_info=True,
                    )

            await asyncio.sleep(1.0)

        self._rebuild_running = False
        self.logger.info(
            "Фоновая задача пересоздания записей в постоянном хранилище завершена",
            event="persistent_rebuild_loop_finished",
            status="success",
        )

    async def restore_from_persistent_queue(self) -> None:
        """Восстанавливает очередь из Redis при старте приложения.

        Загружает все операции из Redis очереди и запускает фоновую задачу
        пересоздания, если есть операции для обработки.

        Этот метод должен быть вызван после создания ImageStorageUnitOfWork
        и инициализации Redis, но до начала работы с изображениями.

        Note:
            Метод безопасен к повторным вызовам - проверяет состояние перед запуском.
        """
        if self._rebuild_running:
            self.logger.debug(
                "Фоновая задача пересоздания уже запущена, пропуск восстановления",
                event="persistent_rebuild_restore_skipped",
                status="info",
            )
            return

        try:
            operations = await self._failed_cache_queue.peek_all()

            if not operations:
                self.logger.debug(
                    "Очередь пересоздания записей в постоянном хранилище пуста при восстановлении",
                    event="persistent_rebuild_restore_empty",
                    status="info",
                )
                return

            self.logger.info(
                f"Восстановлено {len(operations)} операций из Redis очереди пересоздания",
                event="persistent_rebuild_restored",
                status="success",
                count=len(operations),
            )

            # Запускаем фоновую задачу для обработки восстановленных операций
            if not self._rebuild_running:
                self._start_background_rebuild_task()
            else:
                self.logger.warning(
                    "Фоновая задача уже запущена при восстановлении очереди",
                    event="persistent_rebuild_restore_warning",
                    status="warning",
                )

        except Exception as e:
            self.logger.error(
                f"Ошибка при восстановлении очереди из Redis: {e}",
                event="persistent_rebuild_restore_error",
                status="error",
                exc_info=True,
            )
            # Не пробрасываем исключение - приложение должно продолжать работу
            # даже если восстановление очереди не удалось
