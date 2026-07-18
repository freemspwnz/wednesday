from collections.abc import Awaitable, Callable

from httpx2 import AsyncClient, Response

from app.exceptions import AppError, UnexpectedHttpError
from app.protocols import HttpMetrics, Logger

from .errors import map_httpx_error
from .policy import ResiliencePolicy


class HttpClient:
    """Thin adapter over httpx2.AsyncClient with resilience policy and metrics."""

    def __init__(
        self,
        *,
        client: AsyncClient,
        policy: ResiliencePolicy,
        metrics: HttpMetrics,
        logger: Logger,
    ) -> None:
        self._client = client
        self._policy = policy
        self._metrics = metrics
        self._logger = logger.bind(module=self.__class__.__name__)

    @property
    def raw(self) -> AsyncClient:
        """Underlying httpx2 client for flows that bypass the resilience policy (e.g. OAuth)."""
        return self._client

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, **kwargs: object) -> Response:
        return await self._request(self._client.get, path, **kwargs)

    async def post(self, path: str, **kwargs: object) -> Response:
        return await self._request(self._client.post, path, **kwargs)

    async def put(self, path: str, **kwargs: object) -> Response:
        return await self._request(self._client.put, path, **kwargs)

    async def patch(self, path: str, **kwargs: object) -> Response:
        return await self._request(self._client.patch, path, **kwargs)

    async def delete(self, path: str, **kwargs: object) -> Response:
        return await self._request(self._client.delete, path, **kwargs)

    async def _request(
        self,
        method: Callable[..., Awaitable[Response]],
        path: str,
        **kwargs: object,
    ) -> Response:
        relative_path = path.lstrip("/")
        url = str(self._client.base_url.join(relative_path))

        self._logger.debug(
            "HTTP request",
            method=method.__name__,
            url=url,
            timeout=kwargs.get("timeout"),
        )

        async def send() -> Response:
            response = await method(relative_path, **kwargs)
            response.raise_for_status()
            return response

        self._metrics.on_request(method=method.__name__, url=url)

        try:
            response = await self._policy.apply(send)
            self._metrics.on_response(method=method.__name__, url=url, status_code=response.status_code)
            return response
        except AppError as exc:
            self._metrics.on_error(method=method.__name__, url=url, exc=exc)
            raise
        except Exception as exc:
            self._metrics.on_error(method=method.__name__, url=url, exc=exc)
            mapped = map_httpx_error(exc, method=method.__name__, url=url)
            if isinstance(mapped, UnexpectedHttpError):
                self._logger.error(
                    "HTTP request failed",
                    method=method.__name__,
                    url=url,
                    error=str(mapped),
                    exc_info=True,
                )
            raise mapped from exc
