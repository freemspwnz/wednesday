"""
Асинхронный клиент PostgreSQL с пулом подключений для всего приложения.

Дизайн:
- Используем фабрику PostgresPoolFactory для создания и управления пулом подключений.
- Фабрика инкапсулирует состояние пула вместо использования глобальных переменных.
- Остальной код получает пул через Dependency Injection из container.py или main.py.

Поведение при ошибках:
- При неудачной инициализации логируем подробную ошибку и пробрасываем её дальше —
  запуск приложения должен явно решать, считать ли Postgres критичным.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import asyncpg

from infra.logging.logger import get_logger
from shared.config import Config

logger = get_logger(__name__)


class PostgresPoolFactory:
    """Фабрика для создания и управления пулом подключений PostgreSQL.

    Инкапсулирует состояние пула вместо использования глобальных переменных.
    Обеспечивает singleton-поведение в рамках одного экземпляра фабрики.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Инициализирует фабрику пула.

        Args:
            config: Конфигурация для создания пула. Если None, используется глобальный Config.
        """
        self._config = config
        self._pool: asyncpg.Pool | None = None
        self._pool_loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    async def get_pool(
        self,
        *,
        min_size: int = 1,
        max_size: int = 10,
        **connect_kwargs: object,
    ) -> asyncpg.Pool:
        """Получает или создаёт пул подключений.

        Args:
            min_size: Минимальный размер пула.
            max_size: Максимальный размер пула.
            **connect_kwargs: Дополнительные параметры для asyncpg.create_pool.

        Returns:
            Инициализированный пул подключений.

        Raises:
            Exception: При ошибке подключения или проверки соединения.
        """
        async with self._lock:
            if self._pool is not None:
                # Проверяем, что пул создан в текущем event loop
                current_loop = asyncio.get_running_loop()
                if self._pool_loop is not None and self._pool_loop is current_loop:
                    return self._pool
                # Если пул создан в другом loop, возвращаем его (для совместимости)
                logger.debug("Пул Postgres был создан в другом event loop, но не пересоздаём его")
                return self._pool

            # Создаём новый пул
            config = self._config
            if config is None:
                from shared.config import Config

                config = Config()

            if isinstance(config, Config):
                user = config.postgres.user
                password = config.postgres.password
                database = config.postgres.db
                host = config.postgres.host
                port = config.postgres.port
            else:
                user = config.postgres_user
                password = config.postgres_password
                database = config.postgres_db
                host = config.postgres_host
                port = config.postgres_port

            # Создаём базу данных, если она не существует
            await ensure_database(config=config)

            # ВАЖНО: используем database (POSTGRES_DB), а не user (POSTGRES_USER) в DSN
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"

            logger.info(
                f"Инициализация пула Postgres (host={host}, port={port}, min_size={min_size}, max_size={max_size})",
            )

            try:
                self._pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=min_size,
                    max_size=max_size,
                    **connect_kwargs,
                )

                # Быстрая проверка соединения
                async with self._pool.acquire() as conn:
                    await conn.execute("SELECT 1;")

                # Сохраняем ссылку на event loop, в котором был создан пул
                current_loop = asyncio.get_running_loop()
                self._pool_loop = current_loop

                logger.info("Пул подключений Postgres успешно инициализирован")
                return self._pool
            except Exception as exc:  # pragma: no cover - защитное логирование
                logger.error(f"Не удалось инициализировать пул Postgres: {exc}")
                # На всякий случай обнуляем пул, чтобы не оставить битое состояние
                self._pool = None
                raise

    async def close(self) -> None:
        """Закрывает пул подключений."""
        async with self._lock:
            if self._pool is not None:
                try:
                    # Проверяем, что event loop еще работает
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_closed():
                            logger.warning("Event loop уже закрыт, пропускаем закрытие пула Postgres")
                            self._pool = None
                            self._pool_loop = None
                            return
                    except RuntimeError:
                        # Нет работающего event loop
                        logger.warning("Нет работающего event loop, пропускаем закрытие пула Postgres")
                        self._pool = None
                        self._pool_loop = None
                        return

                    await self._pool.close()
                    logger.info("Пул Postgres успешно закрыт")
                except RuntimeError as exc:
                    error_msg = str(exc)
                    if "Event loop is closed" in error_msg:
                        logger.warning("Event loop закрыт во время закрытия пула Postgres — это нормально при shutdown")
                    else:
                        logger.error(f"RuntimeError при закрытии пула Postgres: {exc}")
                except Exception as exc:  # pragma: no cover - защитное логирование
                    logger.error(f"Ошибка при закрытии пула Postgres: {exc}")
                finally:
                    self._pool = None
                    self._pool_loop = None


@dataclass
class PoolMetrics:
    """Метрики пула подключений PostgreSQL."""

    size: int  # Текущий размер пула
    idle_size: int  # Количество свободных соединений
    min_size: int  # Минимальный размер
    max_size: int  # Максимальный размер
    active_connections: int  # Активные соединения (size - idle_size)


def get_pool_metrics(pool: asyncpg.Pool) -> PoolMetrics:
    """Возвращает метрики пула подключений.

    Args:
        pool: Пул подключений PostgreSQL (обязательный параметр).

    Returns:
        PoolMetrics с метриками пула.

    Raises:
        ValueError: Если pool равен None.
    """
    if pool is None:
        raise ValueError("pool не может быть None. Используйте Dependency Injection для передачи пула.")

    return PoolMetrics(
        size=pool.get_size(),
        idle_size=pool.get_idle_size(),
        min_size=pool.get_min_size(),
        max_size=pool.get_max_size(),
        active_connections=pool.get_size() - pool.get_idle_size(),
    )


async def ensure_database(config: Config | None = None) -> None:
    """Создаёт базу данных, если она не существует.

    Подключается к системной базе 'postgres' для проверки и создания
    целевой базы данных перед инициализацией пула подключений.

    Args:
        config: Экземпляр Config. Если None, используется глобальный config.

    Raises:
        asyncpg.InvalidPasswordError: При неверном пароле для подключения.
        asyncpg.PostgresError: При ошибке PostgreSQL при создании базы данных.
        Exception: При неожиданной ошибке при проверке/создании базы данных.
    """
    if config is None:
        from shared.config import Config

        config = Config()

    if isinstance(config, Config):
        user = config.postgres.user
        password = config.postgres.password
        database = config.postgres.db
        host = config.postgres.host
        port = config.postgres.port
    else:
        user = config.postgres_user
        password = config.postgres_password
        database = config.postgres_db
        host = config.postgres_host
        port = config.postgres_port

    # Подключаемся к системной базе 'postgres' для проверки существования целевой БД
    system_dsn = f"postgresql://{user}:{password}@{host}:{port}/postgres"

    logger.info(f"Проверка существования базы данных '{database}' (host={host}, port={port})...")

    try:
        # Создаём временное подключение к системной базе
        conn = await asyncpg.connect(system_dsn)
        try:
            # Проверяем, существует ли база данных
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                database,
            )

            if exists:
                logger.info(f"База данных '{database}' уже существует")
            else:
                logger.info(f"База данных '{database}' не найдена, создаём...")
                # Создаём базу данных
                # Используем параметризованный запрос через format для имени БД
                # (asyncpg не поддерживает параметризацию для CREATE DATABASE)
                await conn.execute(f'CREATE DATABASE "{database}"')
                logger.info(f"База данных '{database}' успешно создана")
        finally:
            await conn.close()
    except asyncpg.InvalidPasswordError:
        logger.error(f"Неверный пароль для подключения к PostgreSQL (пользователь: {user})")
        raise
    except asyncpg.PostgresError as exc:
        if "already exists" in str(exc).lower():
            logger.info(f"База данных '{database}' уже существует (обнаружено при создании)")
        else:
            logger.error(f"Ошибка PostgreSQL при проверке/создании базы данных: {exc}")
            raise
    except Exception as exc:
        logger.error(f"Неожиданная ошибка при проверке/создании базы данных: {exc}", exc_info=True)
        raise
