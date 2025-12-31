"""Сервис для управления очередью непересозданных кэшей в Redis.

Инфраструктурный сервис для персистентного хранения операций пересоздания кэша.
Использует Redis List для хранения операций.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import redis.asyncio as redis

from shared.base.redis_backend_service import RedisBackendService
from shared.protocols.infrastructure import ILogger

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

    Ключ в Redis: `{prefix}queue` (по умолчанию `failed_cache:queue`)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        prefix: str = "failed_cache:",
        logger: ILogger | None = None,
    ) -> None:
        """Инициализирует очередь.

        Args:
            redis_client: Redis клиент (передаётся через Dependency Injection).
            prefix: Префикс для ключей Redis (по умолчанию "failed_cache:").
            logger: Логгер (опционально, создаётся автоматически если None).
        """
        super().__init__(redis_client=redis_client, prefix=prefix, logger=logger)
        self._queue_key = self._key("queue")

    async def enqueue(self, operation: FailedCacheOperation) -> None:
        """Добавляет операцию в очередь.

        Args:
            operation: Операция пересоздания кэша.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            operation_json = operation.to_json()
            await self._redis.rpush(self._queue_key, operation_json)  # type: ignore[misc]

            self.logger.debug(
                "Операция добавлена в очередь пересоздания кэша",
                event="failed_cache_enqueued",
                status="queued",
                cache_key=operation.cache_key,
                storage_path=operation.storage_path,
            )
        except Exception as e:
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

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            result = await self._redis.lpop(self._queue_key)  # type: ignore[misc]

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

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            results = await self._redis.lrange(self._queue_key, 0, -1)  # type: ignore[misc]
            results = results or []

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

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            return int(await self._redis.llen(self._queue_key))  # type: ignore[misc]
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

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            await self._redis.delete(self._queue_key)

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
