"""
Хранилище временного состояния пользователя на базе Redis.

Назначение:
- Сохранять ephemeral‑состояние пользователя (шаги диалога, последние действия и т.п.).
- Поддерживать TTL для автоматической очистки "зависших" состояний.

Дизайн:
- Для гибкости используется JSON‑blob в виде SET/GET, а не HSET/HGETALL.
  Это упрощает эволюцию структуры состояния без миграций схемы.
- TTL реализуется через EXPIRE на ключе.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from services.base.redis_backend_service import RedisBackendService

if TYPE_CHECKING:
    import redis.asyncio as redis

    from utils.redis_client import _InMemoryRedis

    RedisBackend = redis.Redis | _InMemoryRedis


class UserStateCache(RedisBackendService):
    """
    Кэш временного состояния пользователя.
    """

    def __init__(
        self,
        redis_client: RedisBackend,
        *,
        prefix: str = "user_state:",
    ) -> None:
        """Инициализирует хранилище временного состояния пользователя.

        Args:
            redis_client: Экземпляр redis.asyncio.Redis или совместимого клиента.
            prefix: Префикс ключей для хранения состояний (по умолчанию "user_state:").
        """
        super().__init__(redis_client=redis_client, prefix=prefix)

    def _user_key(self, user_id: int) -> str:
        """Формирует ключ для состояния пользователя.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            Полный ключ с префиксом.
        """
        return self._key(str(user_id))

    async def set_state(self, user_id: int, state: dict[str, Any], ttl: int | None = None) -> None:
        """Сохраняет состояние пользователя как JSON-blob.

        Сохраняет состояние пользователя в Redis в формате JSON. При ошибке Redis
        автоматически переходит на in-memory fallback.

        Args:
            user_id: Идентификатор пользователя в Telegram.
            state: Словарь с состоянием пользователя для сохранения.
            ttl: Время жизни состояния в секундах. Если None, состояние живёт
                до явного сброса.

        Note:
            TTL применяется через EXPIRE к ключу в Redis. При ошибке Redis сохранение
            выполняется в in-memory fallback.
        """
        key = self._user_key(user_id)
        payload = json.dumps(state, ensure_ascii=False)

        async def _set_operation(backend: RedisBackend) -> None:
            if ttl is not None:
                await backend.set(key, payload, ex=ttl)
            else:
                await backend.set(key, payload)

        await self._execute_with_fallback(_set_operation)

    async def get_state(self, user_id: int) -> dict[str, Any] | None:
        """Возвращает состояние пользователя или None.

        Извлекает состояние пользователя из Redis. При ошибке Redis автоматически
        проверяет in-memory fallback.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            Словарь с состоянием пользователя или None, если состояние не найдено
            или произошла ошибка декодирования JSON.

        Note:
            При ошибке Redis проверка выполняется в in-memory fallback. При ошибке
            декодирования JSON возвращается None и логируется предупреждение.
        """
        key = self._user_key(user_id)

        async def _get_operation(backend: RedisBackend) -> bytes | str | None:
            return await backend.get(key)

        raw = await self._execute_with_fallback(_get_operation)

        if raw is None:
            return None

        # Преобразуем bytes в str для json.loads
        if isinstance(raw, bytes):
            raw_str: str = raw.decode("utf-8")
        else:
            raw_str = str(raw)

        try:
            value: dict[str, Any] = json.loads(raw_str)
        except json.JSONDecodeError:
            self.logger.warning(
                f"Не удалось декодировать состояние пользователя {user_id} как JSON, состояние сброшено",
            )
            return None
        return value

    async def clear_state(self, user_id: int) -> None:
        """Полностью очищает состояние пользователя.

        Удаляет состояние пользователя из Redis и из in-memory fallback.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Note:
            При ошибке Redis удаление выполняется только в fallback кэше.
        """
        key = self._user_key(user_id)

        async def _delete_operation(backend: RedisBackend) -> None:
            await backend.delete(key)

        await self._execute_with_fallback(_delete_operation)
