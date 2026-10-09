"""Tests for TELEGRAM__PROXY_URL."""

import pytest
from pydantic import SecretStr, ValidationError

from infra.config import Config
from infra.config.observe import MetricsConfig
from infra.config.presentation import TelegramConfig


@pytest.mark.unit
class TestTelegramProxyUrl:
    def test_default_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TELEGRAM__PROXY_URL", raising=False)
        assert TelegramConfig().proxy_url is None

    def test_empty_string_is_none(self) -> None:
        assert TelegramConfig(proxy_url="").proxy_url is None  # type: ignore[arg-type]

    def test_missing_env_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TELEGRAM__PROXY_URL", raising=False)
        cfg = Config(_env_file=None, ENV="DEV", metrics=MetricsConfig(enabled=False))
        assert cfg.telegram.proxy_url is None

    def test_env_http_url_with_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEGRAM__PROXY_URL", "http://user:pass@3x-ui:3128")
        cfg = Config(_env_file=None, ENV="DEV", metrics=MetricsConfig(enabled=False))
        assert cfg.telegram.proxy_url is not None
        assert cfg.telegram.proxy_url.get_secret_value() == "http://user:pass@3x-ui:3128"

    def test_http_url_without_credentials(self) -> None:
        cfg = TelegramConfig(proxy_url="http://host:3128")  # type: ignore[arg-type]
        assert cfg.proxy_url is not None
        assert cfg.proxy_url.get_secret_value() == "http://host:3128"

    @pytest.mark.parametrize("raw", ["https://host:3128", "socks5://host:1080", "ftp://host", "http://"])
    def test_rejects_non_http_proxy(self, raw: str) -> None:
        with pytest.raises(ValidationError, match="TELEGRAM__PROXY_URL"):
            TelegramConfig(proxy_url=raw)  # type: ignore[arg-type]

    def test_secret_hidden_in_repr(self) -> None:
        cfg = TelegramConfig(proxy_url="http://user:s3cret@host:3128")  # type: ignore[arg-type]
        assert isinstance(cfg.proxy_url, SecretStr)
        assert "s3cret" not in repr(cfg)
