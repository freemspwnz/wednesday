"""Application service для обеспечения идемпотентности операций.

Обеспечивает выполнение операций с проверкой идемпотентности через кэширование результатов.
Используется для предотвращения дублирования выполнения задач в Celery.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from shared.base.base_service import BaseService
from shared.protocols import IIdempotencyService, ILogger

if TYPE_CHECKING:
    from infra.redis.redis_client import RedisClient

T = TypeVar("T")


class IdempotencyService(BaseService, IIdempotencyService):
    """Application service для обеспечения идемпотентности операций.

    Использует Redis для кэширования результатов операций и предотвращения
    дублирования выполнения. Соблюдает границы слоёв: использует протокол ICache
    вместо прямого доступа к Redis.
    """

    def __init__(
        self,
        redis_client: RedisClient,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис идемпотентности.

        Args:
            redis_client: Redis-клиент для кэширования результатов.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._redis_client = redis_client

    async def execute_with_idempotency(
        self,
        key: str,
        ttl: int,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Выполняет операцию с проверкой идемпотентности.

        Если операция с данным ключом уже выполнялась и результат кэширован,
        возвращает кэшированный результат. Иначе выполняет операцию и кэширует результат.

        Args:
            key: Уникальный ключ идемпотентности для операции.
            ttl: Время жизни кэшированного результата в секундах.
            operation: Асинхронная операция для выполнения (callable без аргументов).

        Returns:
            Результат выполнения операции (из кэша или новый).

        Raises:
            ValueError: Если формат кэшированного результата невалиден.
            Exception: При ошибке выполнения операции или работы с кэшем.
        """
        cache_key = f"celery:idempotency:{key}"

        # Проверяем кэш
        cached_result = await self._redis_client.get(cache_key)
        if cached_result:
            self.logger.info(
                f"Idempotency cache hit for key={key}",
                event="idempotency_cache_hit",
                status="success",
                cache_key=cache_key,
            )
            try:
                # Десериализуем результат из JSON
                cached_data: dict[str, Any] = json.loads(cached_result)
                # Возвращаем десериализованный результат
                # Тип T будет проверен на уровне использования
                # Для TypedDict (FrogRequestResult) возвращаем dict напрямую
                return cached_data  # type: ignore[return-value]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                self.logger.error(
                    f"Invalid cached result format for key={key}: {e}",
                    event="idempotency_cache_invalid",
                    status="error",
                    cache_key=cache_key,
                    error_type=type(e).__name__,
                )
                raise ValueError(f"Invalid cached result format: {e}") from e

        # Выполняем операцию
        result = await operation()

        # Кэшируем результат
        try:
            # Сериализуем результат в JSON
            # Предполагаем, что результат сериализуем в dict (TypedDict)
            if isinstance(result, dict):
                result_dict: dict[str, Any] = result
            # Для других типов преобразуем в dict
            # Используем asdict для dataclass или __dict__ для объектов
            elif hasattr(result, "__dict__"):
                result_dict = dict(result.__dict__)
            elif hasattr(result, "_asdict"):  # для NamedTuple
                result_dict = dict(result._asdict())
            else:
                # Fallback: оборачиваем в dict
                result_dict = {"result": result}

            await self._redis_client.set(
                cache_key,
                json.dumps(result_dict),
                ex=ttl,
            )

            self.logger.info(
                f"Idempotency cache set for key={key} with ttl={ttl}s",
                event="idempotency_cache_set",
                status="success",
                cache_key=cache_key,
                ttl=ttl,
            )
        except (TypeError, ValueError) as e:
            # Ошибка сериализации не критична - логируем и продолжаем
            self.logger.warning(
                f"Failed to cache result for key={key}: {e}",
                event="idempotency_cache_set_failed",
                status="warning",
                cache_key=cache_key,
                error_type=type(e).__name__,
            )

        return result
