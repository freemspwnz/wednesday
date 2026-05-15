"""Тесты setup_logging и хуков (infra.observe.loguru.setup)."""

from __future__ import annotations

import asyncio
import logging
import sys
from io import StringIO
from pathlib import Path
from types import TracebackType
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from infra.config import LoggingConfig
from infra.observe.loguru.setup import (
    _asyncio_exception_handler,
    _sys_exception_handler,
    setup_logging,
)


def _minimal_config(**kwargs: object) -> LoggingConfig:
    defaults: dict[str, object] = {
        "level": "DEBUG",
        "serialize": False,
        "to_file": False,
        "noisy_libs": ["lib_a", "lib_b"],
    }
    defaults.update(kwargs)
    return LoggingConfig.model_validate(defaults)


@pytest.mark.unit
class TestSetupLoggingCore:
    def test_configures_console_sink_and_logs_banner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cfg = _minimal_config(level="INFO", format="{message}")
        setup_logging(cfg, env="TEST", version="1.2.3", secrets=[])

        assert "Logging configured" in buf.getvalue()
        assert "ENV=TEST" in buf.getvalue()
        assert "LEVEL=INFO" in buf.getvalue()

    def test_patcher_masks_secrets_in_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cfg = _minimal_config(format="{message}")
        setup_logging(cfg, env="DEV", version="0", secrets=["SECRET_TOKEN"])

        logger.info("hello SECRET_TOKEN world")

        out = buf.getvalue()
        assert "SECRET_TOKEN" not in out
        assert "****" in out

    def test_to_file_adds_second_sink(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stdout", StringIO())
        log_path = tmp_path / "app.log"
        cfg = _minimal_config(to_file=True, file_path=log_path, format="{message}")
        setup_logging(cfg, env="DEV", version="0", secrets=[])

        logger.info("file-line")
        text = log_path.read_text(encoding="utf-8")
        assert "file-line" in text

    def test_noisy_libs_get_warning_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stdout", StringIO())
        cfg = _minimal_config(noisy_libs=["httpx", "sqlalchemy"])
        setup_logging(cfg, env="DEV", version="0", secrets=[])

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("sqlalchemy").level == logging.WARNING

    def test_idempotent_second_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cfg = _minimal_config(format="{message}")
        setup_logging(cfg, env="DEV", version="0", secrets=[])
        setup_logging(cfg, env="DEV", version="0", secrets=[])

        # не должно падать; один поток сообщений о конфигурации (по одному на вызов)
        assert buf.getvalue().count("Logging configured") == 2


@pytest.mark.unit
class TestSysExcepthook:
    def test_keyboard_interrupt_delegates_to_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[object] = []

        def fake_original(*args: object) -> None:
            called.append(args)

        monkeypatch.setattr(sys, "__excepthook__", fake_original)
        ki = KeyboardInterrupt()
        _sys_exception_handler(KeyboardInterrupt, ki, cast(TracebackType, None))

        assert len(called) == 1

    def test_uncaught_logs_critical_via_loguru(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cfg = _minimal_config(format="{message}")
        setup_logging(cfg, env="DEV", version="0", secrets=[])

        try:
            raise RuntimeError("oops")
        except RuntimeError:
            _t, v, tb = sys.exc_info()
        assert v is not None and tb is not None
        _sys_exception_handler(RuntimeError, v, tb)

        assert "Uncaught exception" in buf.getvalue()
        assert "RuntimeError" in buf.getvalue() or "oops" in buf.getvalue()


@pytest.mark.unit
class TestAsyncioExceptionHandler:
    def test_with_exception_uses_opt(self) -> None:
        exc = ValueError("ctx")
        with patch("infra.observe.loguru.setup.logger") as mock_logger:
            opt = MagicMock()
            mock_logger.opt.return_value = opt
            loop = MagicMock()
            _asyncio_exception_handler(loop, {"message": "task died", "exception": exc})

            mock_logger.opt.assert_called_once_with(exception=exc)
            opt.error.assert_called_once()

    def test_without_exception_logs_context(self) -> None:
        with patch("infra.observe.loguru.setup.logger") as mock_logger:
            loop = MagicMock()
            ctx = {"message": "no exc", "foo": 1}
            _asyncio_exception_handler(loop, ctx)

            mock_logger.error.assert_called_once()


@pytest.mark.unit
class TestSetupLoggingAsyncioLoop:
    def test_sets_loop_exception_handler_when_loop_running(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stdout", StringIO())

        async def body() -> None:
            cfg = _minimal_config()
            setup_logging(cfg, env="ASYNC", version="9", secrets=[])
            handler = asyncio.get_running_loop().get_exception_handler()
            assert handler is _asyncio_exception_handler

        asyncio.run(body())

    def test_no_running_loop_still_configures_logging(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        cfg = _minimal_config(format="{message}")
        setup_logging(cfg, env="SYNC", version="1", secrets=[])
        assert "Logging configured" in buf.getvalue()
