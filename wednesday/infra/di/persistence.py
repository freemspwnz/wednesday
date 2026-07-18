import asyncio
from functools import cached_property

from redis.asyncio import Redis

from app.protocols import CacheRepoRegistry, UoWFactory
from infra.config import Config
from infra.persistence.redis import (
    RedisRepoRegistry,
    build_redis,
    close_redis,
)
from infra.persistence.sqlalchemy import SQLAUoWFactory
from infra.persistence.yaml import YamlCatalogFactory

from .observe import ObserveContainer


class PersistenceContainer:
    """Container for creating persistence layer."""

    _SHUTDOWN_TIMEOUT = 7.0

    def __init__(
        self,
        *,
        config: Config,
        observe: ObserveContainer,
    ) -> None:
        self._config = config
        self._observe = observe
        self._logger = observe.logger.bind(module=self.__class__.__name__)

    @cached_property
    def uow_factory(self) -> UoWFactory:
        return SQLAUoWFactory(
            config=self._config.postgres,
            metrics=self._observe.metrics.db,
            logger=self._observe.logger,
        )

    @cached_property
    def cache(self) -> CacheRepoRegistry:
        prefix = f"wednesday:{self._config.env}:{self._config.version}:ctx"
        return RedisRepoRegistry(
            redis=self.redis,
            key_prefix=prefix,
            metrics=self._observe.metrics.cache,
            logger=self._observe.logger,
        )

    @cached_property
    def redis(self) -> Redis:
        return build_redis(
            config=self._config.redis,
            logger=self._observe.logger,
        )

    @cached_property
    def catalog(self) -> YamlCatalogFactory:
        return YamlCatalogFactory(
            config=self._config.yaml,
            logger=self._observe.logger,
        )

    async def shutdown(self) -> None:
        self._logger.info("Shutting down persistence container...")

        try:
            async with asyncio.timeout(self._SHUTDOWN_TIMEOUT):
                tasks = []

                if self.__dict__.get("uow_factory") is not None:
                    tasks.append(self.uow_factory.aclose())
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
