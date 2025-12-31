"""
Единый асинхронный клиент Redis для всего приложения.

Дизайн:
- Используем фабрику RedisClientFactory для создания и управления Redis клиентом.
- Фабрика инкапсулирует состояние клиента вместо использования глобальных переменных.
- Остальной код получает клиент через Dependency Injection из container.py или main.py.
- Redis является обязательным компонентом - ошибки подключения пробрасываются наружу.

Почему один клиент:
- Клиент `redis.asyncio.Redis` сам управляет пулом подключений.
- Создание клиента на каждый запрос приводит к лишним TCP‑подключениям и утечкам ресурсов.
- Единый клиент упрощает конфигурацию и позволяет централизованно отслеживать доступность Redis.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeAlias, cast

import redis.asyncio as redis

from infra.logging.logger import get_logger
from shared.config import Config

logger = get_logger(__name__)


# Публичный тип для использования в DI
RedisClient: TypeAlias = redis.Redis


class RedisClientFactory:
    """Фабрика для создания и управления Redis клиентом.

    Инкапсулирует состояние клиента вместо использования глобальных переменных.
    Обеспечивает singleton-поведение в рамках одного экземпляра фабрики.
    Redis является обязательным компонентом - ошибки подключения пробрасываются наружу.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Инициализирует фабрику Redis клиента.

        Args:
            config: Конфигурация для создания клиента. Если None, используется глобальный Config.
        """
        self._config = config
        self._client: redis.Redis | None = None
        self._lock = asyncio.Lock()

    async def get_client(
        self,
        url: str | None = None,
        *,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        **kwargs: object,
    ) -> redis.Redis:
        """Получает или создаёт Redis клиент.

        Args:
            url: URL Redis (приоритет над host/port/db/password).
            host: Хост Redis.
            port: Порт Redis.
            db: Номер базы данных.
            password: Пароль Redis.
            **kwargs: Дополнительные параметры для redis.Redis.

        Returns:
            Инициализированный Redis клиент.

        Raises:
            Exception: При ошибке подключения к Redis.
        """
        async with self._lock:
            if self._client is not None:
                return self._client

            config = self._config
            if config is None:
                from shared.config import Config

                config = Config()

            # Используем переданные параметры или берём из config
            if url is None:
                if isinstance(config, Config):
                    url = config.redis.url
                    if url is None:
                        DEFAULT_REDIS_PORT = 6379
                        host = host if host != "localhost" else config.redis.host
                        port = port if port != DEFAULT_REDIS_PORT else config.redis.port
                        db = db if db != 0 else config.redis.db
                        password = password if password is not None else config.redis.password
                else:
                    url = getattr(config, "redis_url", None)
                    if url is None:
                        DEFAULT_REDIS_PORT = 6379
                        host = host if host != "localhost" else getattr(config, "redis_host", "localhost")
                        port = port if port != DEFAULT_REDIS_PORT else getattr(config, "redis_port", DEFAULT_REDIS_PORT)
                        db = db if db != 0 else getattr(config, "redis_db", 0)
                        password = password if password is not None else getattr(config, "redis_password", None)

            if url:
                client = cast(redis.Redis, redis.from_url(url, decode_responses=True, **kwargs))
            else:
                client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=True,
                    **cast(dict[str, Any], kwargs),
                )

            await client.ping()
            self._client = client
            logger.info(
                f"Подключение к Redis установлено (url={url!r}, host={host!r}, port={port!r}, db={db!r})",
            )
            return client

    async def close(self) -> None:
        """Закрывает Redis клиент."""
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.close()
                    logger.info("Соединение с Redis закрыто")
                except Exception:
                    logger.error("Ошибка при закрытии соединения с Redis", exc_info=True)
                finally:
                    self._client = None

    def is_available(self) -> bool:
        """Проверяет, инициализирован ли Redis клиент.

        Returns:
            True если клиент инициализирован, False в противном случае.
        """
        return self._client is not None


def get_redis_url(config: Config | None = None) -> str | None:
    """Возвращает URL Redis для использования в Celery.

    Используется для настройки Celery broker и backend.
    Формирует URL из переменных окружения или конфигурации.

    Args:
        config: Экземпляр Config. Если None, используется глобальный config.

    Returns:
        URL Redis в формате redis://host:port/db или redis://password@host:port/db.
        Если Redis не настроен, возвращает None.
    """
    from shared.config import Config

    if config is None:
        config = Config()

    if isinstance(config, Config):
        redis_url = config.redis.url
        redis_host = config.redis.host
        redis_port = config.redis.port
        redis_db = config.redis.db
        redis_password = config.redis.password
    else:
        redis_url = config.redis_url
        redis_host = config.redis_host
        redis_port = config.redis_port
        redis_db = config.redis_db
        redis_password = config.redis_password

    if redis_url:
        return redis_url

    # Формируем URL из отдельных параметров
    # Проверяем, что password не пустая строка и не None
    # ВАЖНО: Экранируем пароль через urllib.parse.quote для корректной работы с Celery/kombu
    # Специальные символы в пароле (например, !) могут ломать парсинг URL
    if redis_password and redis_password.strip():
        from urllib.parse import quote

        password_encoded = quote(redis_password, safe="")
        password_part = f":{password_encoded}@"
    else:
        password_part = ""
    return f"redis://{password_part}{redis_host}:{redis_port}/{redis_db}"
