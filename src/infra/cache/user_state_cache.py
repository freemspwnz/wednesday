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
from typing import Any

import redis.asyncio as redis

from shared.base.redis_backend_service import RedisBackendService


class UserStateCache(RedisBackendService):
    """
    Кэш временного состояния пользователя.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        prefix: str = "user_state:",
    ) -> None:
        """Инициализирует хранилище временного состояния пользователя.

        Args:
            redis_client: Экземпляр redis.asyncio.Redis.
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

        Сохраняет состояние пользователя в Redis в формате JSON.

        Args:
            user_id: Идентификатор пользователя в Telegram.
            state: Словарь с состоянием пользователя для сохранения.
            ttl: Время жизни состояния в секундах. Если None, состояние живёт
                до явного сброса.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        key = self._user_key(user_id)
        payload = json.dumps(state, ensure_ascii=False)
        if ttl is not None:
            await self._redis.set(key, payload, ex=ttl)
        else:
            await self._redis.set(key, payload)

    async def get_state(self, user_id: int) -> dict[str, Any] | None:
        """Возвращает состояние пользователя или None.

        Извлекает состояние пользователя из Redis.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            Словарь с состоянием пользователя или None, если состояние не найдено
            или произошла ошибка декодирования JSON.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        key = self._user_key(user_id)
        raw = await self._redis.get(key)

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

        Удаляет состояние пользователя из Redis.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        key = self._user_key(user_id)
        await self._redis.delete(key)
