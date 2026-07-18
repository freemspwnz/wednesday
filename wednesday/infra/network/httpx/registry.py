from functools import cached_property

from httpx2 import Timeout

from app.protocols import Logger
from infra.config import Config, HttpConfig

from .factory import HttpClientFactory
from .providers import SberAuth, SberClient


class ProvidersRegistry:
    """Lazy registry of outbound HTTP provider clients."""

    def __init__(
        self,
        *,
        config: Config,
        factory: HttpClientFactory,
        logger: Logger,
    ) -> None:
        self._config = config
        self._factory = factory
        self._logger = logger.bind(module=self.__class__.__name__)

    @cached_property
    def sber(self) -> SberClient:
        config = self._config.gigachat
        client = self._factory(
            http=config.http,
            retrier=config.retrier,
            breaker=config.breaker,
            limiter=config.limiter,
        )
        auth = SberAuth(
            client=client.raw,
            url=config.auth_url,
            key=config.auth_key.get_secret_value(),
            scope=config.scope,
            logger=self._logger,
        )
        timeouts = self._timeouts(config.http)
        return SberClient(
            client=client,
            auth=auth,
            timeouts=timeouts,
            logger=self._logger,
        )

    async def aclose(self) -> None:
        sber = self.__dict__.get("sber")
        if sber is None:
            return

        try:
            await self._factory.aclose(sber.client)
        finally:
            self.__dict__.pop("sber", None)

    @staticmethod
    def _timeouts(config: HttpConfig) -> dict[str, Timeout]:
        timeouts: dict[str, Timeout] = {}
        for key, value in config.timeouts.items():
            timeouts[key] = Timeout(
                timeout=value.timeout,
                connect=value.connect,
                read=value.read,
                write=value.write,
                pool=value.pool,
            )
        return timeouts
