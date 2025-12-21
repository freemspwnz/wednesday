from __future__ import annotations

from typing import Any

import pytest

import main


class _DummyConfig:
    """Простая заглушка конфига для проверки инициализации Sentry без чтения ENV."""

    def __init__(self, dsn: str | None) -> None:
        self.sentry_dsn = dsn
        self.sentry_environment = "test"
        self.sentry_release = "1.2.3"


def test_init_sentry_called_when_dsn_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверяем, что при наличии SENTRY_DSN вызывается sentry_sdk.init с корректными аргументами."""
    calls: dict[str, Any] = {}

    def _fake_init(*args: object, **kwargs: object) -> None:
        calls["args"] = args
        calls["kwargs"] = kwargs

    # Подменяем глобальный config в main на заглушку с нужными полями.
    monkeypatch.setattr(main, "config", _DummyConfig(dsn="https://public@example.com/1"), raising=False)
    monkeypatch.setattr("sentry_sdk.init", _fake_init, raising=False)

    logger = main.get_logger(__name__)
    main._init_sentry(logger)

    # Убедимся, что init был вызван и получил наш DSN.
    assert "kwargs" in calls
    kwargs = calls["kwargs"]
    assert kwargs.get("dsn") == "https://public@example.com/1"
    assert kwargs.get("environment") == "test"
    assert kwargs.get("release") == "1.2.3"


def test_init_sentry_skipped_when_no_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """При отсутствии SENTRY_DSN sentry_sdk.init не должен вызываться."""
    calls: dict[str, Any] = {"called": False}

    def _fake_init(*args: object, **kwargs: object) -> None:
        calls["called"] = True

    monkeypatch.setattr(main, "config", _DummyConfig(dsn=None), raising=False)
    monkeypatch.setattr("sentry_sdk.init", _fake_init, raising=False)

    logger = main.get_logger(__name__)
    main._init_sentry(logger)

    assert calls["called"] is False
