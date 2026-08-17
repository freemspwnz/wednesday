"""Tests for HttpClient adapter."""

from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock

import httpx2
import pytest

from app.exceptions import HttpResponseError, HttpTimeoutError, TooManyRequests
from infra.network.httpx.client import HttpClient
from infra.network.httpx.policy import ResiliencePolicy

from .conftest import PassThroughBreaker, PassThroughLimiter, PassThroughRetrier, T


def _client(
    *,
    handler: httpx2.MockTransport,
    metrics: MagicMock,
    logger: MagicMock,
) -> HttpClient:
    raw = httpx2.AsyncClient(
        transport=handler,
        base_url="https://api.example.com/v1/",
    )
    policy = ResiliencePolicy(
        retrier=PassThroughRetrier(),
        breaker=PassThroughBreaker(),
        limiter=PassThroughLimiter(),
    )
    return HttpClient(client=raw, policy=policy, metrics=metrics, logger=logger)


@pytest.mark.unit
class TestHttpClient:
    @pytest.mark.asyncio
    async def test_get_success_emits_metrics(self, mock_http_metrics: MagicMock, mock_logger: MagicMock) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            assert request.url.path == "/v1/models"
            return httpx2.Response(200, json={"ok": True})

        client = _client(handler=httpx2.MockTransport(handler), metrics=mock_http_metrics, logger=mock_logger)
        try:
            response = await client.get("/models")
            assert response.status_code == 200
            mock_http_metrics.on_request.assert_called_once()
            mock_http_metrics.on_response.assert_called_once()
            assert mock_http_metrics.on_response.call_args.kwargs["status_code"] == 200
            mock_http_metrics.on_error.assert_not_called()
            mock_logger.warning.assert_not_called()
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_http_status_error_is_mapped(self, mock_http_metrics: MagicMock, mock_logger: MagicMock) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(503, request=request, json={"reason": "overloaded"})

        client = _client(handler=httpx2.MockTransport(handler), metrics=mock_http_metrics, logger=mock_logger)
        try:
            with pytest.raises(HttpResponseError) as exc_info:
                await client.get("/boom")
            assert exc_info.value.status_code == 503
            assert "overloaded" in exc_info.value.body
            mock_http_metrics.on_error.assert_called_once()
            mock_logger.warning.assert_called_once()
            logged = mock_logger.warning.call_args
            assert logged.args[0] == "HTTP response error"
            assert logged.kwargs["status_code"] == 503
            assert "overloaded" in logged.kwargs["response_body"]
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_app_error_from_policy_is_reraised(
        self,
        mock_http_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        class BlockingLimiter(PassThroughLimiter):
            def __call__(
                self,
                limit: object,
                *args: str,
                cost: int = 1,
            ) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
                _ = limit, args, cost

                def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
                    async def wrapper(*a: object, **k: object) -> T:
                        _ = func, a, k
                        raise TooManyRequests(retry_after=1, reset_at=0.0, limit="base")

                    return wrapper

                return decorator

        raw = httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda r: httpx2.Response(200)),
            base_url="https://api.example.com/",
        )
        client = HttpClient(
            client=raw,
            policy=ResiliencePolicy(
                retrier=PassThroughRetrier(),
                breaker=PassThroughBreaker(),
                limiter=BlockingLimiter(),
            ),
            metrics=mock_http_metrics,
            logger=mock_logger,
        )
        try:
            with pytest.raises(TooManyRequests):
                await client.get("/x")
            mock_http_metrics.on_error.assert_called_once()
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_timeout_is_mapped(self, mock_http_metrics: MagicMock, mock_logger: MagicMock) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ReadTimeout("slow", request=request)

        client = _client(handler=httpx2.MockTransport(handler), metrics=mock_http_metrics, logger=mock_logger)
        try:
            with pytest.raises(HttpTimeoutError):
                await client.post("/chat")
        finally:
            await client.aclose()
