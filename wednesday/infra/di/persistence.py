import asyncio
from functools import cached_property

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.protocols import CacheClient, CacheRepoRegistry, UoW
from infra.config import Config
from infra.persistence.redis import (
    RedisClient,
    RedisRepoRegistry,
    build_redis,
    close_redis,
)
from infra.persistence.sqlalchemy import (
    SQLAUoW,
    close_engine,
    create_engine,
)

from .observe import ObserveContainer

_PERSISTENCE_SHUTDOWN_TIMEOUT = 7.0


class PersistenceContainer:
    """Контейнер для создания persistence-слоя."""

    def __init__(
        self,
        *,
        config: Config,
        observe: ObserveContainer,
    ) -> None:
        self._config = config
        self._observe = observe
        self._logger = observe.logger.bind(module=self.__class__.__name__)

    def uow_factory(self) -> UoW:
        return SQLAUoW(self._session_factory)

    @cached_property
    def cache_repo_registry(self) -> CacheRepoRegistry:
        cache_prefix = f"wednesday:{self._config.env}:{self._config.version}:ctx"
        return RedisRepoRegistry(
            client=self._cache_client,
            logger=self._observe.logger,
            key_prefix=cache_prefix,
        )

    @cached_property
    def redis(self) -> Redis:
        return build_redis(
            config=self._config.redis,
            logger=self._observe.logger,
        )

    @cached_property
    def _cache_client(self) -> CacheClient:
        return RedisClient(
            redis=self.redis,
            metrics=self._observe.metrics_registry.cache_metrics,
            logger=self._observe.logger,
        )

    @cached_property
    def _session_factory(self) -> async_sessionmaker:
        return async_sessionmaker(
            bind=self._db_engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @cached_property
    def _db_engine(self) -> AsyncEngine:
        engine = create_engine(
            config=self._config.postgres,
            logger=self._observe.logger,
        )
        self._observe.metrics_registry.db_metrics.register(engine.sync_engine)
        return engine

    async def shutdown(self) -> None:
        self._logger.info("Shutting down persistence container...")

        try:
            async with asyncio.timeout(_PERSISTENCE_SHUTDOWN_TIMEOUT):
                tasks = []

                if self.__dict__.get("_db_engine") is not None:
                    tasks.append(close_engine(engine=self._db_engine, logger=self._observe.logger))
                if self.__dict__.get("redis") is not None:
                    tasks.append(close_redis(redis=self.redis, logger=self._observe.logger))

                failed = False

                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, Exception):
                            self._logger.error(f"Resource shutdown task failed: {res}")
                            failed = True

                if not failed:
                    self._logger.debug("Persistence container shutdown completed successfully")

        except TimeoutError:
            self._logger.warning("Persistence container shutdown timed out! Forced exit.", exc_info=True)
        except Exception:
            self._logger.warning("Unexpected error during persistence container shutdown", exc_info=True)
        finally:
            self._logger.info("Persistence container shut down")
