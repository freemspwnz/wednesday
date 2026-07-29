"""Tests for LoguruLogger and get_logger (infra.observe.loguru.logger)."""

from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import LogMessageFormatError
from app.protocols import Logger
from infra.config import LoggingConfig
from infra.observe.loguru.logger import LoguruLogger, get_logger


@pytest.fixture
def mock_core() -> tuple[MagicMock, MagicMock, MagicMock]:
    core = MagicMock()
    opt = MagicMock()
    bound = MagicMock()
    core.opt.return_value = opt
    opt.bind.return_value = bound
    return core, opt, bound


@pytest.fixture
def logging_config() -> LoggingConfig:
    return LoggingConfig.model_validate(
        {
            "level": "DEBUG",
            "serialize": False,
            "to_file": False,
        },
    )


@pytest.mark.unit
class TestGetLogger:
    def test_calls_setup_logging_and_returns_logger_with_unknown_module(
        self,
        logging_config: LoggingConfig,
    ) -> None:
        with patch("infra.observe.loguru.logger.setup_logging") as setup:
            lg = get_logger(
                config=logging_config,
                env="TEST",
                version="1.0.0",
                secrets=["secret"],
            )

        setup.assert_called_once_with(logging_config, "TEST", "1.0.0", ["secret"])
        assert isinstance(lg, LoguruLogger)
        assert lg._bound_context["module"] == "unknown"

    def test_return_satisfies_logger_protocol(self, logging_config: LoggingConfig) -> None:
        with patch("infra.observe.loguru.logger.setup_logging"):
            lg = get_logger(
                config=logging_config,
                env="t",
                version="0",
                secrets=[],
            )
        assert isinstance(lg, Logger)


@pytest.mark.unit
class TestLoguruLoggerLevels:
    def test_all_level_methods_route_to_log(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, bound = mock_core
        lg = LoguruLogger(core)

        lg.trace("t")
        lg.debug("d")
        lg.info("i")
        lg.success("s")
        lg.warning("w")
        lg.error("e")
        lg.critical("c")

        levels = [c.args[0] for c in bound.log.call_args_list]
        assert levels == ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]

    def test_log_passes_level(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, bound = mock_core
        lg = LoguruLogger(core)
        lg.log("INFO", "msg")
        bound.log.assert_called_with("INFO", "msg")

    def test_opt_uses_depth_and_exception_none(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, _ = mock_core
        lg = LoguruLogger(core)
        lg.info("x")
        core.opt.assert_called_with(depth=2, exception=None)


@pytest.mark.unit
class TestLoguruLoggerFormatting:
    def test_message_formatted_with_args(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, bound = mock_core
        lg = LoguruLogger(core)
        lg.info("v={}", 99)
        bound.log.assert_called_with("INFO", "v=99")

    def test_invalid_format_raises_log_message_format_error(
        self,
        mock_core: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        lg = LoguruLogger(mock_core[0])
        with pytest.raises(LogMessageFormatError):
            lg.info("{broken", "a")


@pytest.mark.unit
class TestLoguruLoggerExtraAndException:
    def test_extra_fields_passed_to_bind(
        self,
        mock_core: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        core, opt, _ = mock_core
        lg = LoguruLogger(core)
        lg.info("m", user_id=1, chat_id=2, generation_id="g", other="extra")

        bind_kw = opt.bind.call_args.kwargs
        assert bind_kw["module"] == "unknown"
        assert bind_kw["user_id"] == 1
        assert bind_kw["chat_id"] == 2
        assert bind_kw["generation_id"] == "g"
        assert bind_kw["other"] == "extra"

    def test_exception_sets_exc_info_by_default(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, _ = mock_core
        lg = LoguruLogger(core)
        lg.exception("fail")
        core.opt.assert_called_with(depth=2, exception=True)

    def test_exception_respects_explicit_exc_info_false(
        self,
        mock_core: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        core, _, _ = mock_core
        lg = LoguruLogger(core)
        lg.exception("fail", exc_info=False)
        core.opt.assert_called_with(depth=2, exception=False)

    def test_exc_info_kw_passed_to_opt(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, _ = mock_core
        lg = LoguruLogger(core)
        exc = ValueError("x")
        lg.error("e", exc_info=exc)
        core.opt.assert_called_with(depth=2, exception=exc)


@pytest.mark.unit
class TestLoguruLoggerBind:
    def test_bind_returns_new_instance_with_merged_context(
        self,
        mock_core: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        core, _, _ = mock_core
        base = LoguruLogger(core, bound_context={"module": "a", "x": 1})
        child = base.bind(y=2)
        assert child is not base
        assert isinstance(child, LoguruLogger)
        assert child._bound_context == {"module": "a", "x": 1, "y": 2}

    def test_child_overrides_bound_keys(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, _ = mock_core
        base = LoguruLogger(core, bound_context={"module": "m", "k": 1})
        child = base.bind(k=2)
        assert isinstance(child, LoguruLogger)
        assert child._bound_context["k"] == 2

    def test_default_module_unknown_when_missing(self, mock_core: tuple[MagicMock, MagicMock, MagicMock]) -> None:
        core, _, _ = mock_core
        lg = LoguruLogger(core, bound_context={})
        assert lg._bound_context["module"] == "unknown"
