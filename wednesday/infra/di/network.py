import asyncio
from functools import cached_property

from infra.config import Config
from infra.network.httpx import HttpClientFactory, ProvidersRegistry

from .observe import ObserveContainer
from .resilience import ResilienceContainer


class NetworkContainer:
    """Container wiring network layer."""

    _SHUTDOWN_TIMEOUT = 5.0

    def __init__(
        self,
        *,
        config: Config,
        resilience: ResilienceContainer,
        observe: ObserveContainer,
    ) -> None:
        self._config = config
        self._resilience = resilience
        self._observe = observe
        self._logger = observe.logger.bind(module=self.__class__.__name__)

    @cached_property
    def providers(self) -> ProvidersRegistry:
        factory = HttpClientFactory(
            retrier=self._resilience.retrier,
            breaker=self._resilience.breaker,
            limiter=self._resilience.limiter,
            metrics=self._observe.metrics.http,
            logger=self._observe.logger,
        )
        return ProvidersRegistry(
            config=self._config,
            factory=factory,
            logger=self._observe.logger,
        )

    async def shutdown(self) -> None:
        self._logger.info("Shutting down network container...")
        try:
            async with asyncio.timeout(self._SHUTDOWN_TIMEOUT):
                if self.__dict__.get("providers") is not None:
                    await self.providers.aclose()
                self._logger.debug("HTTP client closed successfully")
        except TimeoutError:
            self._logger.warning("Network container shutdown timed out! Forced exit.")
        except Exception:
            self._logger.warning("Unexpected error while shutting down network container", exc_info=True)
        finally:
            self._logger.info("Network container shut down")
