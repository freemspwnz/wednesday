"""Tests for SberAuth OAuth flow."""

import time
from unittest.mock import MagicMock

import httpx2
import pytest

from app.exceptions import HttpAuthError
from infra.network.httpx.providers.sber.auth import SberAuth


@pytest.mark.unit
class TestSberAuth:
    @pytest.mark.asyncio
    async def test_fetches_token_and_sets_bearer(self, mock_logger: MagicMock) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            if "oauth" in str(request.url):
                return httpx2.Response(
                    200,
                    json={"access_token": "tok-1", "expires_at": int((time.time() + 3600) * 1000)},
                )
            return httpx2.Response(200, json={"ok": True})

        raw = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        auth = SberAuth(
            client=raw,
            url="https://auth.example.com/oauth",
            key="basic-key",
            scope="GIGACHAT_API_PERS",
            logger=mock_logger,
        )
        try:
            flow = auth.async_auth_flow(httpx2.Request("GET", "https://api.example.com/models"))
            request = await anext(flow)
            assert request.headers["Authorization"] == "Bearer tok-1"
            with pytest.raises(StopAsyncIteration):
                await flow.asend(httpx2.Response(200, request=request))
        finally:
            await raw.aclose()

    @pytest.mark.asyncio
    async def test_refreshes_token_on_401(self, mock_logger: MagicMock) -> None:
        tokens = {"n": 0}

        def handler(request: httpx2.Request) -> httpx2.Response:
            if "oauth" in str(request.url):
                tokens["n"] += 1
                return httpx2.Response(
                    200,
                    json={
                        "access_token": f"tok-{tokens['n']}",
                        "expires_at": int((time.time() + 3600) * 1000),
                    },
                )
            return httpx2.Response(200)

        raw = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        auth = SberAuth(
            client=raw,
            url="https://auth.example.com/oauth",
            key="basic-key",
            scope="GIGACHAT_API_PERS",
            logger=mock_logger,
        )
        try:
            flow = auth.async_auth_flow(httpx2.Request("GET", "https://api.example.com/x"))
            first = await anext(flow)
            assert first.headers["Authorization"] == "Bearer tok-1"
            second = await flow.asend(httpx2.Response(401, request=first))
            assert second.headers["Authorization"] == "Bearer tok-2"
            with pytest.raises(StopAsyncIteration):
                await flow.asend(httpx2.Response(200, request=second))
            assert tokens["n"] == 2
        finally:
            await raw.aclose()

    @pytest.mark.asyncio
    async def test_invalid_token_payload_raises_auth_error(self, mock_logger: MagicMock) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, json={"not": "a-token"})

        raw = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        auth = SberAuth(
            client=raw,
            url="https://auth.example.com/oauth",
            key="basic-key",
            scope="GIGACHAT_API_PERS",
            logger=mock_logger,
        )
        try:
            flow = auth.async_auth_flow(httpx2.Request("GET", "https://api.example.com/x"))
            with pytest.raises(HttpAuthError):
                await anext(flow)
        finally:
            await raw.aclose()

    @pytest.mark.asyncio
    async def test_oauth_http_error_logs_response_body(self, mock_logger: MagicMock) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(401, json={"error": "invalid_client"})

        raw = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        auth = SberAuth(
            client=raw,
            url="https://auth.example.com/oauth",
            key="basic-key",
            scope="GIGACHAT_API_PERS",
            logger=mock_logger,
        )
        try:
            flow = auth.async_auth_flow(httpx2.Request("GET", "https://api.example.com/x"))
            with pytest.raises(HttpAuthError):
                await anext(flow)
            mock_logger.warning.assert_called_once()
            logged = mock_logger.warning.call_args
            assert logged.args[0] == "OAuth HTTP response error"
            assert logged.kwargs["status_code"] == 401
            assert "invalid_client" in logged.kwargs["response_body"]
        finally:
            await raw.aclose()
