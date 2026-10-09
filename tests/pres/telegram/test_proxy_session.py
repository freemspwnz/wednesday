"""AiohttpSession accepts an optional HTTP proxy URL."""

import pytest
from aiogram.client.session.aiohttp import AiohttpSession


@pytest.mark.unit
class TestAiohttpProxySession:
    def test_none_keeps_direct_session(self) -> None:
        session = AiohttpSession(proxy=None)
        assert session.proxy is None

    def test_http_proxy_is_stored(self) -> None:
        url = "http://user:pass@127.0.0.1:3128"
        session = AiohttpSession(proxy=url)
        assert session.proxy == url
