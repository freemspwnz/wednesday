"""Tests for map_httpx_error."""

import httpx2
import pytest

from app.exceptions import (
    AppError,
    HttpResponseError,
    HttpTimeoutError,
    HttpTransportError,
    UnexpectedHttpError,
)
from infra.network.httpx.errors import map_httpx_error


@pytest.mark.unit
class TestMapHttpxError:
    def test_passthrough_app_error(self) -> None:
        exc = AppError("already mapped")
        assert map_httpx_error(exc, method="GET", url="https://x") is exc

    def test_timeout(self) -> None:
        mapped = map_httpx_error(httpx2.ReadTimeout("t"), method="GET", url="https://x/a")
        assert isinstance(mapped, HttpTimeoutError)
        assert mapped.method == "GET"
        assert mapped.url == "https://x/a"

    def test_transport(self) -> None:
        mapped = map_httpx_error(httpx2.ConnectError("down"), method="POST", url="https://x")
        assert isinstance(mapped, HttpTransportError)

    def test_http_status(self) -> None:
        request = httpx2.Request("GET", "https://x/y")
        response = httpx2.Response(503, request=request)
        exc = httpx2.HTTPStatusError("boom", request=request, response=response)
        mapped = map_httpx_error(exc, method="GET", url="https://x/y")
        assert isinstance(mapped, HttpResponseError)
        assert mapped.status_code == 503

    def test_generic_http_error(self) -> None:
        mapped = map_httpx_error(httpx2.HTTPError("x"), method="GET", url="https://x")
        assert isinstance(mapped, UnexpectedHttpError)

    def test_unknown_exception(self) -> None:
        mapped = map_httpx_error(RuntimeError("x"), method="GET", url="https://x")
        assert isinstance(mapped, UnexpectedHttpError)
