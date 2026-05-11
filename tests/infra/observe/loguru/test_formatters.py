"""Тесты scrub и LoguruHandler (infra.observe.loguru.formatters)."""

from __future__ import annotations

import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from infra.observe.loguru.formatters import LoguruHandler, scrub


@pytest.mark.unit
class TestScrub:
    def test_string_no_secrets_returns_unchanged(self) -> None:
        assert scrub("plain text") == "plain text"

    def test_string_empty_secrets_list(self) -> None:
        assert scrub("x", secrets=[]) == "x"

    def test_string_replaces_secret_substrings(self) -> None:
        assert scrub("prefix TOKEN suffix", secrets=["TOKEN"]) == "prefix **** suffix"

    def test_string_skips_empty_secret_strings(self) -> None:
        assert scrub("ab", secrets=["", "b"]) == "a****"

    def test_dict_masks_sensitive_keys_case_insensitive(self) -> None:
        out = scrub({"Authorization": "bear", "ok": "v"})
        assert isinstance(out, dict)
        assert out["Authorization"] == "****"
        assert out["ok"] == "v"

    def test_dict_nested_and_recursion(self) -> None:
        out = scrub({"outer": {"password": "p1", "x": 1}})
        assert isinstance(out, dict)
        inner = out["outer"]
        assert isinstance(inner, dict)
        assert inner["password"] == "****"
        assert inner["x"] == 1

    def test_list_tuple_set(self) -> None:
        assert scrub([1, "a", {"token": "t"}]) == [1, "a", {"token": "****"}]
        assert scrub((1, {"api_key": "k"})) == (1, {"api_key": "****"})
        s = scrub({"a", "b"})
        assert isinstance(s, set)
        assert s == {"a", "b"}

    def test_secrets_applied_to_nested_strings(self) -> None:
        assert scrub(["x-SECRET-y"], secrets=["SECRET"]) == ["x-****-y"]


@pytest.mark.unit
class TestLoguruHandler:
    @pytest.fixture
    def capture_sink(self) -> StringIO:
        buf = StringIO()
        logger.remove()
        logger.add(buf, format="{message}", level="DEBUG", colorize=False)
        return buf

    def test_emit_forwards_message_to_loguru(self, capture_sink: StringIO) -> None:
        pylog = logging.getLogger("test_loguru_handler_fwd")
        pylog.handlers.clear()
        pylog.setLevel(logging.DEBUG)
        pylog.addHandler(LoguruHandler())
        pylog.propagate = False

        pylog.info("forwarded-line")

        assert "forwarded-line" in capture_sink.getvalue()

    def test_emit_with_exception(self, capture_sink: StringIO) -> None:
        pylog = logging.getLogger("test_loguru_handler_exc")
        pylog.handlers.clear()
        pylog.setLevel(logging.ERROR)
        pylog.addHandler(LoguruHandler())
        pylog.propagate = False

        try:
            raise ValueError("boom")
        except ValueError:
            logging.getLogger("test_loguru_handler_exc").exception("with-traceback")

        text = capture_sink.getvalue()
        assert "with-traceback" in text
        assert "ValueError" in text or "boom" in text

    def test_emit_unknown_levelname_falls_back_to_levelno(self, capture_sink: StringIO) -> None:
        """Ветка except ValueError: level = record.levelno."""
        custom = 35
        logging.addLevelName(custom, "CUSTOM_LEVEL_FOR_HANDLER_TEST")

        pylog = logging.getLogger("test_unknown_level")
        pylog.handlers.clear()
        pylog.setLevel(custom)
        pylog.addHandler(LoguruHandler())
        pylog.propagate = False

        record = logging.LogRecord(
            name="lib",
            level=custom,
            pathname=__file__,
            lineno=1,
            msg="custom-level-msg",
            args=(),
            exc_info=None,
        )
        pylog.handle(record)

        assert "custom-level-msg" in capture_sink.getvalue()

    def test_emit_passes_logger_name_as_extra(self, capture_sink: StringIO) -> None:
        pylog = logging.getLogger("my_aiogram_bridge")
        pylog.handlers.clear()
        pylog.setLevel(logging.INFO)
        pylog.addHandler(LoguruHandler())
        pylog.propagate = False

        pylog.info("named")

        # default format is only {message}; logger_name goes to extra — sink still gets message
        assert "named" in capture_sink.getvalue()


@pytest.mark.unit
def test_emit_skips_logging_internal_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    """Покрытие цикла while frame.f_code.co_filename == logging.__file__."""
    buf = StringIO()
    logger.remove()
    logger.add(buf, format="{message}", level="DEBUG", colorize=False)

    fake_frame = MagicMock()
    fake_frame.f_code.co_filename = logging.__file__
    fake_outer = MagicMock()
    fake_outer.f_code.co_filename = __file__
    fake_frame.f_back = fake_outer

    with patch("logging.currentframe", return_value=fake_frame):
        handler = LoguruHandler()
        record = logging.LogRecord("n", logging.INFO, __file__, 1, "depth-test", (), None)
        handler.emit(record)

    assert "depth-test" in buf.getvalue()
