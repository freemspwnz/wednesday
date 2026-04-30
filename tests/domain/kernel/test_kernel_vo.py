from datetime import UTC, datetime, timedelta

import pytest

from domain.kernel import AwareDatetime, NonEmptyStr, ValidationError


@pytest.mark.unit
def test_non_empty_str_rejects_blank_value() -> None:
    with pytest.raises(ValidationError):
        NonEmptyStr("   ")


@pytest.mark.unit
def test_non_empty_str_trims_surrounding_spaces() -> None:
    value = NonEmptyStr("  hello  ")
    assert value.value == "hello"
    assert str(value) == "hello"


@pytest.mark.unit
def test_aware_datetime_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        AwareDatetime(datetime(2026, 1, 1, 12, 0))


@pytest.mark.unit
def test_aware_datetime_add_timedelta() -> None:
    dt = AwareDatetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    assert dt + timedelta(hours=1) == AwareDatetime(datetime(2026, 1, 1, 13, 0, tzinfo=UTC))


@pytest.mark.unit
def test_aware_datetime_subtract_timedelta() -> None:
    dt = AwareDatetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    assert dt - timedelta(hours=1) == AwareDatetime(datetime(2026, 1, 1, 11, 0, tzinfo=UTC))


@pytest.mark.unit
def test_aware_datetime_subtract_aware_datetime_returns_timedelta() -> None:
    left = AwareDatetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    right = AwareDatetime(datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
    assert left - right == timedelta(hours=2)


@pytest.mark.unit
def test_aware_datetime_string_and_repr() -> None:
    dt = AwareDatetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    assert str(dt) == "2026-01-01T12:00:00+00:00"
    assert "AwareDatetime(" in repr(dt)


@pytest.mark.unit
def test_aware_datetime_now_utc_and_from_datetime() -> None:
    now = AwareDatetime.now_utc()
    assert now.value.tzinfo is not None

    from_dt = AwareDatetime.from_datetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    assert from_dt == AwareDatetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
