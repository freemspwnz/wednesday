"""LimitsMetrics tests."""

from unittest.mock import MagicMock

import pytest

from infra.observe.prometheus.adapters.rl import LimitsMetrics


@pytest.mark.unit
class TestLimitsMetrics:
    def test_on_call(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_call(limiter="telegram", bucket="chat", limit="10/hour", result=True)
        assert coll.observe.call_args.kwargs["labels"] == {"limiter": "telegram", "bucket": "chat"}
        assert coll.increment.call_args.kwargs["labels"] == {
            "limiter": "telegram",
            "bucket": "chat",
            "limit": "10/hour",
            "result": "success",
        }
        assert "name" not in coll.increment.call_args.kwargs["labels"]

    def test_on_get_stats_success(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_get_stats(limiter="telegram", bucket="chat", reset_time=123.0, remaining=3)
        assert coll.set_gauge.call_count == 2
        assert coll.set_gauge.call_args.kwargs["labels"] == {"limiter": "telegram", "bucket": "chat"}
        succ = coll.increment.call_args.kwargs["labels"]
        assert succ["result"] == "success"
        assert succ["limiter"] == "telegram"
        assert succ["bucket"] == "chat"

    def test_on_reset(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_reset(limiter="telegram", bucket="chat", limit=100)
        assert coll.increment.call_args.kwargs["name"] == "rl_reset_calls_total"
        assert coll.increment.call_args.kwargs["labels"] == {"limiter": "telegram", "bucket": "chat"}

    def test_on_error_records_duration_and_counter(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_error(limiter="telegram", bucket="chat", operation="call", error="storage")
        coll.observe.assert_called_once()
        assert coll.observe.call_args.kwargs["name"] == "rl_calls_duration_seconds"
        assert coll.observe.call_args.kwargs["labels"] == {"limiter": "telegram", "bucket": "chat"}
        coll.increment.assert_called_once_with(
            name="rl_errors_total",
            labels={
                "limiter": "telegram",
                "bucket": "chat",
                "operation": "call",
                "error": "storage",
            },
        )

    def test_on_error_uses_operation_duration_metric(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_error(limiter="telegram", bucket="chat", operation="get_stats", error="unexpected")
        assert coll.observe.call_args.kwargs["name"] == "rl_window_stats_duration_seconds"
        m.on_error(limiter="telegram", bucket="chat", operation="reset", error="storage")
        assert coll.observe.call_args.kwargs["name"] == "rl_resets_duration_seconds"
