import asyncio
from collections.abc import Callable

from httpx2 import AsyncClient, AsyncHTTPTransport, Limits, Timeout

from app.protocols import CircuitBreaker, HttpMetrics, Logger, RateLimiter, Retrier
from infra.config import CircuitBreakerConfig, HttpConfig, RateLimitConfig, RetryConfig

from .client import HttpClient
from .policy import ResiliencePolicy
from .predicate import is_httpx_retryable

_HTTP_CLIENT_CLOSE_TIMEOUT = 5.0


class HttpClientFactory:
    """Build resilient httpx2 clients from HTTP and resilience configs."""

    def __init__(
        self,
        *,
        retrier: Callable[..., Retrier],
        breaker: Callable[..., CircuitBreaker],
        limiter: Callable[..., RateLimiter],
        metrics: HttpMetrics,
        logger: Logger,
    ) -> None:
        self._retrier = retrier
        self._breaker = breaker
        self._limiter = limiter
        self._metrics = metrics
        self._logger = logger.bind(module=self.__class__.__name__)

    def __call__(
        self,
        *,
        http: HttpConfig,
        retrier: RetryConfig,
        breaker: CircuitBreakerConfig,
        limiter: RateLimitConfig,
    ) -> HttpClient:
        self._logger.debug("Building HTTP client...")

        transport = AsyncHTTPTransport()

        limits = Limits(
            max_connections=http.max_connections,
            max_keepalive_connections=http.max_keepalive_connections,
            keepalive_expiry=http.keepalive_expiry,
        )

        timeout = Timeout(
            timeout=http.timeouts["base"].timeout,
            connect=http.timeouts["base"].connect,
            read=http.timeouts["base"].read,
            write=http.timeouts["base"].write,
            pool=http.timeouts["base"].pool,
        )

        client = AsyncClient(
            base_url=http.base_url,
            timeout=timeout,
            limits=limits,
            transport=transport,
            follow_redirects=http.follow_redirects,
            http2=http.http2,
            headers=http.headers,
            verify=http.verify,
        )

        policy = ResiliencePolicy(
            retrier=self._retrier(config=retrier, predicate=is_httpx_retryable),
            breaker=self._breaker(config=breaker),
            limiter=self._limiter(config=limiter),
        )

        return HttpClient(
            client=client,
            policy=policy,
            metrics=self._metrics,
            logger=self._logger,
        )

    async def aclose(self, client: HttpClient) -> None:
        self._logger.debug("Closing HTTP client...")
        try:
            async with asyncio.timeout(_HTTP_CLIENT_CLOSE_TIMEOUT):
                await client.aclose()
            self._logger.debug("HTTP client closed successfully")
        except TimeoutError:
            self._logger.warning("Close HTTP client timed out! Forced exit.", exc_info=True)
        except Exception:
            self._logger.warning("Unexpected error while closing HTTP client", exc_info=True)
        finally:
            self._logger.info("HTTP client closed")
