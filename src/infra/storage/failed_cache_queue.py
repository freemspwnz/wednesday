"""Сервис для управления очередью непересозданных кэшей в Redis.

Инфраструктурный сервис для персистентного хранения операций пересоздания кэша.
Использует Redis List с автоматическим fallback на in-memory при недоступности Redis.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from shared.base.redis_backend_service import RedisBackendService
from shared.protocols import ILogger

if TYPE_CHECKING:
    import redis.asyncio as redis

    from infra.redis.redis_client import _InMemoryRedis

    RedisBackend = redis.Redis | _InMemoryRedis

# Константа для ограничения длины raw_data в логах
MAX_RAW_DATA_LOG_LENGTH = 100


@dataclass
class FailedCacheOperation:
    """Операция пересоздания кэша для хранения в Redis."""

    cache_key: str
    storage_path: str
    caption: str

    def to_json(self) -> str:
        """Сериализует операцию в JSON.

        Returns:
            JSON-строка с данными операции.

        Raises:
            TypeError: При ошибке сериализации.
        """
        try:
            return json.dumps(asdict(self), ensure_ascii=False)
        except (TypeError, ValueError) as e:
            raise TypeError(f"Ошибка сериализации FailedCacheOperation: {e}") from e

    @classmethod
    def from_json(cls, data: str) -> FailedCacheOperation:
        """Десериализует операцию из JSON.

        Args:
            data: JSON-строка с данными операции.

        Returns:
            Экземпляр FailedCacheOperation.

        Raises:
            ValueError: При неверном формате JSON или отсутствии обязательных полей.
        """
        try:
            parsed = json.loads(data)
            # Валидация обязательных полей
            required_fields = {"cache_key", "storage_path", "caption"}
            if not all(field in parsed for field in required_fields):
                missing = required_fields - set(parsed.keys())
                raise ValueError(f"Отсутствуют обязательные поля: {missing}")
            return cls(
                cache_key=str(parsed["cache_key"]),
                storage_path=str(parsed["storage_path"]),
                caption=str(parsed["caption"]),
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Неверный формат JSON: {e}") from e
        except (KeyError, TypeError) as e:
            raise ValueError(f"Неверная структура данных: {e}") from e


class FailedCacheQueue(RedisBackendService):
    """Управление очередью непересозданных кэшей в Redis.

    Использует Redis List для хранения операций пересоздания кэша.
    Автоматически переходит на in-memory fallback при недоступности Redis.

    Ключ в Redis: `{prefix}queue` (по умолчанию `failed_cache:queue`)
    """

    def __init__(
        self,
        redis_client: RedisBackend,
        *,
        prefix: str = "failed_cache:",
        logger: ILogger | None = None,
    ) -> None:
        """Инициализирует очередь.

        Args:
            redis_client: Redis клиент (из get_redis()).
            prefix: Префикс для ключей Redis (по умолчанию "failed_cache:").
            logger: Логгер (опционально, создаётся автоматически если None).
        """
        super().__init__(redis_client=redis_client, prefix=prefix, logger=logger)
        self._queue_key = self._key("queue")

    async def enqueue(self, operation: FailedCacheOperation) -> None:
        """Добавляет операцию в очередь.

        Args:
            operation: Операция пересоздания кэша.

        Note:
            При ошибке Redis автоматически переходит на in-memory fallback.
        """
        try:
            operation_json = operation.to_json()

            async def _enqueue_operation(backend: RedisBackend) -> None:
                await backend.rpush(self._queue_key, operation_json)  # type: ignore[misc]

            await self._execute_with_fallback(
                _enqueue_operation,
                log_on_fallback=True,
            )

            self.logger.debug(
                "Операция добавлена в очередь пересоздания кэша",
                event="failed_cache_enqueued",
                status="queued",
                cache_key=operation.cache_key,
                storage_path=operation.storage_path,
            )
        except Exception as e:
            # Логируем, но не пробрасываем - fallback обработает это
            self.logger.warning(
                f"Не удалось добавить операцию в очередь пересоздания кэша: {e}",
                event="failed_cache_enqueue_error",
                status="error",
                cache_key=operation.cache_key,
                exc_info=True,
            )
            raise

    async def dequeue(self) -> FailedCacheOperation | None:
        """Извлекает операцию из очереди (неблокирующий).

        Returns:
            Операция пересоздания кэша или None, если очередь пуста.

        Note:
            При ошибке десериализации операция пропускается и логируется.
        """
        try:

            async def _dequeue_operation(backend: RedisBackend) -> bytes | str | None:
                result = await backend.lpop(self._queue_key)  # type: ignore[misc]
                return result  # type: ignore[no-any-return]

            result = await self._execute_with_fallback(
                _dequeue_operation,
                log_on_fallback=True,
            )

            if result is None:
                return None

            # Преобразуем bytes в str, если необходимо
            if isinstance(result, bytes):
                result_str = result.decode("utf-8")
            else:
                result_str = str(result)

            try:
                operation = FailedCacheOperation.from_json(result_str)
                self.logger.debug(
                    "Операция извлечена из очереди пересоздания кэша",
                    event="failed_cache_dequeued",
                    status="processing",
                    cache_key=operation.cache_key,
                )
                return operation
            except ValueError as e:
                self.logger.warning(
                    f"Ошибка десериализации операции из очереди: {e}",
                    event="failed_cache_deserialize_error",
                    status="error",
                    raw_data=(
                        result_str[:MAX_RAW_DATA_LOG_LENGTH]
                        if len(result_str) <= MAX_RAW_DATA_LOG_LENGTH
                        else result_str[:MAX_RAW_DATA_LOG_LENGTH] + "..."
                    ),
                    exc_info=True,
                )
                return None

        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при извлечении из очереди: {e}",
                event="failed_cache_dequeue_error",
                status="error",
                exc_info=True,
            )
            return None

    async def peek_all(self) -> list[FailedCacheOperation]:
        """Возвращает все операции из очереди без удаления.

        Используется для восстановления очереди при старте приложения.

        Returns:
            Список операций пересоздания кэша.

        Note:
            Пропускает операции с ошибками десериализации.
        """
        try:

            async def _peek_operation(backend: RedisBackend) -> list[bytes | str]:
                result = await backend.lrange(self._queue_key, 0, -1)  # type: ignore[misc]
                return result or []

            results = await self._execute_with_fallback(
                _peek_operation,
                log_on_fallback=True,
            )

            operations: list[FailedCacheOperation] = []
            skipped = 0

            for item in results:
                # Преобразуем bytes в str
                if isinstance(item, bytes):
                    item_str = item.decode("utf-8")
                else:
                    item_str = str(item)

                try:
                    operation = FailedCacheOperation.from_json(item_str)
                    operations.append(operation)
                except ValueError as e:
                    skipped += 1
                    self.logger.warning(
                        f"Пропущена операция с ошибкой десериализации: {e}",
                        event="failed_cache_peek_deserialize_error",
                        status="warning",
                        raw_data=(
                            item_str[:MAX_RAW_DATA_LOG_LENGTH]
                            if len(item_str) <= MAX_RAW_DATA_LOG_LENGTH
                            else item_str[:MAX_RAW_DATA_LOG_LENGTH] + "..."
                        ),
                    )

            if operations:
                self.logger.info(
                    f"Загружено {len(operations)} операций из очереди пересоздания кэша",
                    event="failed_cache_restored",
                    status="success",
                    count=len(operations),
                    skipped=skipped,
                )
            elif skipped > 0:
                self.logger.warning(
                    f"Все операции в очереди имеют ошибки десериализации (пропущено: {skipped})",
                    event="failed_cache_restore_error",
                    status="error",
                    skipped=skipped,
                )

            return operations

        except Exception as e:
            self.logger.error(
                f"Ошибка при чтении очереди: {e}",
                event="failed_cache_peek_error",
                status="error",
                exc_info=True,
            )
            return []

    async def size(self) -> int:
        """Возвращает размер очереди.

        Returns:
            Количество операций в очереди.
        """
        try:

            async def _size_operation(backend: RedisBackend) -> int:
                return await backend.llen(self._queue_key)  # type: ignore[misc,no-any-return]

            return await self._execute_with_fallback(
                _size_operation,
                log_on_fallback=True,
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при получении размера очереди: {e}",
                event="failed_cache_size_error",
                status="error",
            )
            return 0

    async def clear(self) -> None:
        """Очищает очередь.

        Используется для тестирования и очистки устаревших данных.
        """
        try:

            async def _clear_operation(backend: RedisBackend) -> None:
                await backend.delete(self._queue_key)

            await self._execute_with_fallback(
                _clear_operation,
                log_on_fallback=True,
            )

            self.logger.info(
                "Очередь пересоздания кэша очищена",
                event="failed_cache_cleared",
                status="success",
            )
        except Exception as e:
            self.logger.warning(
                f"Ошибка при очистке очереди: {e}",
                event="failed_cache_clear_error",
                status="error",
                exc_info=True,
            )
