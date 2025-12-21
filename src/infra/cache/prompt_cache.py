"""
Сервис кэширования промптов в Redis.

Основные задачи:
- Хранить недавно сгенерированные промпты (например, для Kandinsky) с TTL.
- Давать быстрый доступ к последним успешным промптам без повторного обращения к GigaChat.
- Работать поверх Redis, но автоматически деградировать в in‑memory режим при недоступности Redis.

Дизайн:
- Ключи в Redis формируются как `<prefix><key>`, где prefix по умолчанию `"prompt:"`.
- Значения сохраняются в виде JSON‑строк, чтобы поддерживать как строки, так и словари.
- TTL задаётся на уровне SET/SETEX; если ttl не указан, используется default_ttl.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from shared.base.redis_backend_service import RedisBackendService
from shared.protocols import ICache

if TYPE_CHECKING:
    import redis.asyncio as redis

    from infra.redis.redis_client import _InMemoryRedis

    RedisBackend = redis.Redis | _InMemoryRedis


class PromptCache(RedisBackendService, ICache[dict | str]):
    """
    Кэш промптов на базе Redis с автоматическим fallback в память.
    """

    def __init__(
        self,
        redis_client: RedisBackend,
        *,
        prefix: str = "prompt:",
        default_ttl: int = 3600,
    ) -> None:
        """Инициализирует кэш промптов.

        Args:
            redis_client: Экземпляр redis.asyncio.Redis или совместимого клиента.
            prefix: Префикс для всех ключей этого кэша (по умолчанию "prompt:").
            default_ttl: Время жизни записей по умолчанию в секундах (по умолчанию 3600).
        """
        super().__init__(redis_client=redis_client, prefix=prefix)
        self._default_ttl = default_ttl

    async def set(self, key: str, prompt: dict | str, ttl: int | None = None) -> None:
        """Сохраняет промпт с TTL.

        Сохраняет промпт в Redis с указанным временем жизни. При ошибке Redis
        автоматически переходит на in-memory fallback.

        Args:
            key: Ключ для сохранения промпта (без префикса).
            prompt: Промпт для сохранения (словарь или строка).
            ttl: Время жизни записи в секундах. Если None, используется default_ttl.

        Note:
            Использует SET с параметром EX в Redis. При RedisError автоматически
            переходит на in-memory fallback для обеспечения отказоустойчивости.
        """
        full_key = self._key(key)
        payload = json.dumps(prompt, ensure_ascii=False)
        ttl_value = ttl if ttl is not None else self._default_ttl

        async def _set_operation(backend: RedisBackend) -> None:
            await backend.set(full_key, payload, ex=ttl_value)

        await self._execute_with_fallback(_set_operation)

    async def get(self, key: str) -> dict | str | None:
        """Возвращает сохранённый промпт или None.

        Извлекает промпт из кэша по ключу. При ошибке Redis автоматически
        проверяет in-memory fallback.

        Args:
            key: Ключ для получения промпта (без префикса).

        Returns:
            Сохранённый промпт (словарь или строка) или None, если ключ не найден.

        Note:
            При ошибке Redis автоматически переходит на in-memory fallback.
        """
        full_key = self._key(key)

        async def _get_operation(backend: RedisBackend) -> bytes | str | None:
            result = await backend.get(full_key)
            return result

        raw = await self._execute_with_fallback(_get_operation)

        if raw is None:
            return None

        # Преобразуем bytes в str для json.loads
        if isinstance(raw, bytes):
            raw_str: str = raw.decode("utf-8")
        else:
            raw_str = str(raw)

        try:
            loaded: Any = json.loads(raw_str)
        except json.JSONDecodeError:
            # В редких случаях можем получить "сырой" текст.
            return raw_str

        # В этом сервисе мы ожидаем либо словарь (JSON‑объект), либо строку.
        if isinstance(loaded, dict):
            return loaded
        if isinstance(loaded, str):
            return loaded
        return str(loaded)

    async def delete(self, key: str) -> None:
        """Удаляет запись из кэша.

        Удаляет промпт из Redis и из in-memory fallback.

        Args:
            key: Ключ для удаления (без префикса).

        Note:
            При ошибке Redis удаление выполняется только в fallback кэше.
        """
        full_key = self._key(key)

        async def _delete_operation(backend: RedisBackend) -> None:
            await backend.delete(full_key)

        await self._execute_with_fallback(_delete_operation)

    async def exists(self, key: str) -> bool:
        """Проверяет наличие ключа в кэше.

        Проверяет существование ключа в Redis. При ошибке Redis проверяет
        in-memory fallback.

        Args:
            key: Ключ для проверки (без префикса).

        Returns:
            True если ключ существует, False в противном случае.

        Note:
            При ошибке Redis проверка выполняется только в fallback кэше.
        """
        full_key = self._key(key)

        async def _exists_operation(backend: RedisBackend) -> int:
            return await backend.exists(full_key)

        exists_val = await self._execute_with_fallback(_exists_operation)
        return bool(exists_val)

    async def keys(self, pattern: str = "*") -> list[str]:
        """Возвращает список ключей (без префикса) по шаблону.

        Выполняет поиск ключей в Redis по шаблону. Возвращает список ключей
        без префикса.

        Args:
            pattern: Шаблон для поиска ключей (по умолчанию "*" для всех ключей).

        Returns:
            Список ключей без префикса, соответствующих шаблону.

        Warning:
            Это вспомогательный метод и не должен использоваться в "горячем" пути,
            так как операция KEYS в Redis — потенциально тяжёлая и может блокировать
            сервер при большом количестве ключей.

        Note:
            При ошибке Redis поиск выполняется только в fallback кэше.
        """
        prefixed_pattern = f"{self._prefix}{pattern}"

        async def _keys_operation(backend: RedisBackend) -> list[bytes | str]:
            keys = await backend.keys(prefixed_pattern)
            # Приводим к нужному типу для mypy
            return cast(list[bytes | str], keys)

        raw_keys = await self._execute_with_fallback(_keys_operation)

        # Преобразуем bytes в str и снимаем префикс, чтобы вернуть "логические" ключи.
        result: list[str] = []
        for k in raw_keys:
            if isinstance(k, bytes):
                k_str = k.decode("utf-8")
            else:
                k_str = k
            if k_str.startswith(self._prefix):
                result.append(k_str[len(self._prefix) :])
        return result
