import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cached_property

from infra.config import Config

from .observe import ObserveContainer
from .persistence import PersistenceContainer
from .resilience import ResilienceContainer
from .scope import ScopeContainer

_SHUTDOWN_TIMEOUT = 10.0


class Container:
    """Composition Root всего приложения.

    Управляет жизненным циклом: init() — создание ресурсов,
    shutdown() — освобождение ресурсов.
    """

    def __init__(
        self,
        *,
        config: Config,
    ) -> None:
        self._config = config
        self._logger = self.observe.logger.bind(module=self.__class__.__name__)

    @cached_property
    def observe(self) -> ObserveContainer:
        return ObserveContainer(
            config=self._config,
        )

    @cached_property
    def persistence(self) -> PersistenceContainer:
        return PersistenceContainer(
            config=self._config,
            observe=self.observe,
        )

    @cached_property
    def resilience(self) -> ResilienceContainer:
        return ResilienceContainer(
            config=self._config,
            observe=self.observe,
            persistence=self.persistence,
        )

    @asynccontextmanager
    async def get_scope(self) -> AsyncIterator["ScopeContainer"]:
        scope = ScopeContainer(
            uow_factory=self.persistence.uow_factory,
            cache_registry=self.persistence.cache_repo_registry,
            logger=self.observe.logger,
        )
        yield scope

    async def shutdown(self) -> None:
        self._logger.info("Shutting down containers...")

        try:
            async with asyncio.timeout(_SHUTDOWN_TIMEOUT):
                tasks = []
                if self.__dict__.get("persistence") is not None:
                    tasks.append(self.persistence.shutdown())

                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, Exception):
                            self._logger.error(f"Shutdown error: {res}")
            self._logger.debug("All containers shutdown completed successfully")
        except TimeoutError:
            self._logger.warning("Shutdown timed out! Some resources might not be closed properly.")
        except Exception:
            self._logger.warning("Unexpected error during shutdown", exc_info=True)
        finally:
            self._logger.info("All containers shut down")
