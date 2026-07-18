"""HttpxMetrics tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import pytest

from infra.observe.prometheus.adapters.http import HttpxMetrics


@pytest.mark.unit
class TestHttpxMetrics:
    def test_on_response_emits_success_labels(self) -> None:
        coll = MagicMock()
        m = HttpxMetrics(collector=coll)
        m.on_request(method="post", url="https://api.example.com/v1/chat?x=1")
        m.on_response(method="post", url="https://api.example.com/v1/chat?x=1", status_code=200)

        labels = coll.increment.call_args.kwargs["labels"]
        assert labels == {
            "method": "POST",
            "url": "https://api.example.com/v1/chat",
            "outcome": "success",
            "status_code": "200",
        }
        coll.observe.assert_called_once()
        assert coll.observe.call_args.kwargs["name"] == "http_request_duration_seconds"
        assert coll.increment.call_args.kwargs["name"] == "http_requests_total"

    def test_on_error_http_status_code_attr(self) -> None:
        coll = MagicMock()
        m = HttpxMetrics(collector=coll)
        m.on_request(method="get", url="https://api.example.com/files/1")
        exc = SimpleNamespace(status_code=503)
        m.on_error(method="get", url="https://api.example.com/files/1", exc=exc)  # type: ignore[arg-type]

        labels = coll.increment.call_args.kwargs["labels"]
        assert labels["outcome"] == "http_error"
        assert labels["status_code"] == "503"

    def test_on_error_timeout(self) -> None:
        coll = MagicMock()
        m = HttpxMetrics(collector=coll)
        m.on_request(method="get", url="https://api.example.com/x")
        m.on_error(
            method="get",
            url="https://api.example.com/x",
            exc=httpx2.ReadTimeout("timed out"),
        )
        labels = coll.increment.call_args.kwargs["labels"]
        assert labels["outcome"] == "timeout"
        assert labels["status_code"] == "0"

    def test_on_error_transport(self) -> None:
        coll = MagicMock()
        m = HttpxMetrics(collector=coll)
        m.on_request(method="get", url="https://api.example.com/x")
        m.on_error(
            method="get",
            url="https://api.example.com/x",
            exc=httpx2.ConnectError("down"),
        )
        labels = coll.increment.call_args.kwargs["labels"]
        assert labels["outcome"] == "connection_error"
        assert labels["status_code"] == "0"

    def test_on_error_app_timeout_by_type_name(self) -> None:
        coll = MagicMock()
        m = HttpxMetrics(collector=coll)

        class HttpTimeoutError(Exception):
            pass

        m.on_request(method="get", url="https://api.example.com/x")
        m.on_error(method="get", url="https://api.example.com/x", exc=HttpTimeoutError("t"))
        assert coll.increment.call_args.kwargs["labels"]["outcome"] == "timeout"

    def test_on_error_unknown(self) -> None:
        coll = MagicMock()
        m = HttpxMetrics(collector=coll)
        m.on_request(method="get", url="https://api.example.com/x")
        m.on_error(method="get", url="https://api.example.com/x", exc=RuntimeError("boom"))
        labels = coll.increment.call_args.kwargs["labels"]
        assert labels["outcome"] == "error"
        assert labels["status_code"] == "0"

    def test_normalize_url_strips_query(self) -> None:
        assert HttpxMetrics._normalize_url("https://host/path?a=1&b=2") == "https://host/path"

    def test_status_code_from_nested_response(self) -> None:
        class _Exc(Exception):
            def __init__(self) -> None:
                super().__init__()
                self.response = SimpleNamespace(status_code=429)

        assert HttpxMetrics._status_code_from_exception(_Exc()) == 429
