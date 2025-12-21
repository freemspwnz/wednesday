"""Unit-тесты для ImageStorageUnitOfWork."""

from __future__ import annotations

import pytest

from app.image_storage_unit_of_work import (
    ImageSaveOperation,
    ImageStorageUnitOfWork,
)
from shared.base.exceptions import StorageError
from shared.protocols import ICache, IImageStorage

pytestmark = [pytest.mark.unit]


class MockCache(ICache[tuple[bytes, str]]):
    """Мок кэша для тестов."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, str]] = {}
        self.set_calls: list[tuple[str, tuple[bytes, str]]] = []
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False
        self.should_fail_get = False
        self.should_fail_delete = False

    async def get(self, key: str) -> tuple[bytes, str] | None:
        """Получает значение из кэша."""
        self.get_calls.append(key)
        if self.should_fail_get:
            raise Exception("Cache get error")
        return self._data.get(key)

    async def set(self, key: str, value: tuple[bytes, str], ttl: int | None = None) -> None:
        """Сохраняет значение в кэш."""
        self.set_calls.append((key, value))
        if self.should_fail_set:
            raise Exception("Cache set error")
        self._data[key] = value

    async def delete(self, key: str) -> None:
        """Удаляет значение из кэша."""
        self.delete_calls.append(key)
        if self.should_fail_delete:
            raise Exception("Cache delete error")
        self._data.pop(key, None)


class MockStorage(IImageStorage):
    """Мок хранилища для тестов."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self.save_calls: list[tuple[bytes, str | None, str]] = []
        self.get_by_path_calls: list[str] = []
        self.get_random_calls: list[str | None] = []
        self.delete_calls: list[str] = []
        self.should_fail_save = False
        self.should_fail_get_by_path = False
        self.should_fail_delete = False
        self.save_counter = 0

    async def save(
        self,
        data: bytes,
        folder: str | None = None,
        prefix: str = "frog",
    ) -> str:
        """Сохраняет данные в хранилище."""
        self.save_calls.append((data, folder, prefix))
        if self.should_fail_save:
            raise StorageError("Storage save error")
        self.save_counter += 1
        path = f"{prefix}_{self.save_counter}.png"
        self._files[path] = data
        return path

    async def get_by_path(self, path: str) -> bytes:
        """Загружает данные по пути."""
        self.get_by_path_calls.append(path)
        if self.should_fail_get_by_path:
            raise StorageError("Storage get_by_path error")
        if path not in self._files:
            raise FileNotFoundError(f"File not found: {path}")
        return self._files[path]

    async def get_random(self, folder: str | None = None) -> tuple[bytes, str] | None:
        """Получает случайный файл."""
        self.get_random_calls.append(folder)
        if not self._files:
            return None
        path = list(self._files.keys())[0]
        return self._files[path], path

    async def delete(self, path: str) -> None:
        """Удаляет файл."""
        self.delete_calls.append(path)
        if self.should_fail_delete:
            raise StorageError("Storage delete error")
        self._files.pop(path, None)


@pytest.mark.asyncio
async def test_save_image_success_both() -> None:
    """Тест успешного сохранения в кэш и хранилище."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    image_data = b"test-image-data"
    caption = "test caption"
    cache_key = "test-key"

    result = await uow.save_image(
        image_data=image_data,
        caption=caption,
        cache_key=cache_key,
    )

    assert result is True
    assert len(storage.save_calls) == 1
    assert len(cache.set_calls) == 1
    assert cache.set_calls[0][0] == cache_key
    assert cache.set_calls[0][1] == (image_data, caption)
    assert len(uow._operations) == 1
    assert uow._operations[0].cache_saved is True
    assert uow._operations[0].storage_saved is True


@pytest.mark.asyncio
async def test_save_image_storage_failure() -> None:
    """Тест ошибки сохранения в хранилище."""
    cache = MockCache()
    storage = MockStorage()
    storage.should_fail_save = True
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    result = await uow.save_image(
        image_data=b"test-data",
        caption="test",
        cache_key="key",
    )

    assert result is False
    assert len(storage.save_calls) == 1
    assert len(cache.set_calls) == 0  # Кэш не должен быть вызван при ошибке хранилища


@pytest.mark.asyncio
async def test_save_image_cache_failure_storage_success() -> None:
    """Тест ошибки сохранения в кэш при успешном сохранении в хранилище."""
    cache = MockCache()
    cache.should_fail_set = True
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    image_data = b"test-image-data"
    caption = "test caption"
    cache_key = "test-key"

    result = await uow.save_image(
        image_data=image_data,
        caption=caption,
        cache_key=cache_key,
    )

    assert result is True  # Операция считается успешной, т.к. хранилище успешно
    assert len(storage.save_calls) == 1
    assert len(cache.set_calls) == 1
    assert uow._operations[0].storage_saved is True
    assert uow._operations[0].cache_saved is False
    # Операция должна быть добавлена в очередь пересоздания
    assert len(uow._failed_cache_operations) == 1
    assert uow._failed_cache_operations[0].cache_key == cache_key


@pytest.mark.asyncio
async def test_rebuild_cache_from_storage_success() -> None:
    """Тест успешного пересоздания кэша из хранилища."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    image_data = b"test-image-data"
    caption = "test caption"
    cache_key = "test-key"
    storage_path = "frog_1.png"

    # Сохраняем файл в хранилище
    await storage.save(image_data, prefix="frog")

    # Пересоздаём кэш
    result = await uow.rebuild_cache_from_storage(
        cache_key=cache_key,
        storage_path=storage_path,
        caption=caption,
    )

    assert result is True
    assert len(storage.get_by_path_calls) == 1
    assert storage.get_by_path_calls[0] == storage_path
    assert len(cache.set_calls) == 1
    assert cache.set_calls[0][0] == cache_key
    assert cache.set_calls[0][1] == (image_data, caption)


@pytest.mark.asyncio
async def test_rebuild_cache_from_storage_file_not_found() -> None:
    """Тест пересоздания кэша при отсутствии файла."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    with pytest.raises(FileNotFoundError):
        await uow.rebuild_cache_from_storage(
            cache_key="test-key",
            storage_path="nonexistent.png",
            caption="test",
        )


@pytest.mark.asyncio
async def test_rebuild_cache_from_storage_no_cache() -> None:
    """Тест пересоздания кэша без кэша."""
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=None, storage=storage)

    result = await uow.rebuild_cache_from_storage(
        cache_key="test-key",
        storage_path="frog_1.png",
        caption="test",
    )

    assert result is False


@pytest.mark.asyncio
async def test_rebuild_cache_from_storage_no_storage() -> None:
    """Тест пересоздания кэша без хранилища."""
    cache = MockCache()
    uow = ImageStorageUnitOfWork(cache=cache, storage=None)

    result = await uow.rebuild_cache_from_storage(
        cache_key="test-key",
        storage_path="frog_1.png",
        caption="test",
    )

    assert result is False


@pytest.mark.asyncio
async def test_background_rebuild_task() -> None:
    """Тест фоновой задачи пересоздания кэша."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    image_data = b"test-image-data"
    caption = "test caption"
    cache_key = "test-key"

    # Сохраняем в хранилище, но кэш не удаётся
    cache.should_fail_set = True
    await uow.save_image(
        image_data=image_data,
        caption=caption,
        cache_key=cache_key,
    )

    # Проверяем, что операция добавлена в очередь
    assert len(uow._failed_cache_operations) == 1
    assert uow._rebuild_running is True

    # Исправляем кэш и ждём завершения фоновой задачи
    cache.should_fail_set = False

    # Ждём завершения фоновой задачи (с таймаутом)
    import asyncio

    for _ in range(10):  # Максимум 10 секунд
        await asyncio.sleep(0.5)
        if not uow._rebuild_running:
            break

    # Проверяем, что кэш был пересоздан
    assert len(uow._failed_cache_operations) == 0
    assert uow._rebuild_running is False
    # Проверяем, что кэш был вызван (через rebuild_cache_from_storage)
    assert len(cache.set_calls) >= 1


@pytest.mark.asyncio
async def test_background_rebuild_task_retry_on_failure() -> None:
    """Тест повторных попыток фоновой задачи при ошибках."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    image_data = b"test-image-data"
    caption = "test caption"
    cache_key = "test-key"

    # Сохраняем в хранилище
    storage_path = await storage.save(image_data, prefix="frog")

    # Добавляем операцию в очередь вручную
    operation = ImageSaveOperation(
        image_data=image_data,
        caption=caption,
        cache_key=cache_key,
        storage_path=storage_path,
        storage_saved=True,
    )
    uow._failed_cache_operations.append(operation)

    # Кэш будет падать первые несколько раз
    call_count = 0

    async def failing_set(key: str, value: tuple[bytes, str], ttl: int | None = None) -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 2:  # Первые 2 вызова падают
            raise Exception("Cache set error")
        await MockCache.set(cache, key, value, ttl)

    cache.set = failing_set  # type: ignore[method-assign]

    # Запускаем фоновую задачу
    uow._start_background_rebuild_task()

    # Ждём завершения (с таймаутом)
    import asyncio

    for _ in range(20):  # Максимум 10 секунд
        await asyncio.sleep(0.5)
        if not uow._rebuild_running and len(uow._failed_cache_operations) == 0:
            break

    # Проверяем, что кэш был пересоздан после retry
    assert len(uow._failed_cache_operations) == 0
    assert call_count >= 2  # Было несколько попыток


@pytest.mark.asyncio
async def test_commit() -> None:
    """Тест метода commit."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    await uow.save_image(
        image_data=b"test-data",
        caption="test",
        cache_key="key",
    )

    result = await uow.commit()
    assert result is True


@pytest.mark.asyncio
async def test_rollback() -> None:
    """Тест метода rollback."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    await uow.save_image(
        image_data=b"test-data",
        caption="test",
        cache_key="key",
    )

    await uow.rollback()

    # Проверяем, что кэш был очищен
    assert len(cache.delete_calls) == 1
    assert cache.delete_calls[0] == "key"
    assert len(uow._operations) == 0


@pytest.mark.asyncio
async def test_clear() -> None:
    """Тест метода clear."""
    cache = MockCache()
    storage = MockStorage()
    uow = ImageStorageUnitOfWork(cache=cache, storage=storage)

    await uow.save_image(
        image_data=b"test-data",
        caption="test",
        cache_key="key",
    )

    uow.clear()
    assert len(uow._operations) == 0
