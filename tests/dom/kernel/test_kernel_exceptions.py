import pytest

from domain.kernel import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    ValidationError,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc_cls",
    [
        DomainError,
        ValidationError,
        InvalidStateTransitionError,
    ],
)
def test_kernel_exceptions_preserve_message(exc_cls: type[DomainError]) -> None:
    exc = exc_cls("problem")
    assert exc.message == "problem"
    assert str(exc) == "problem"


@pytest.mark.unit
def test_access_denied_error_requires_code() -> None:
    exc = AccessDeniedError("insufficient_role")
    assert exc.code == "insufficient_role"
    assert exc.message == "access denied: insufficient_role"
    assert str(exc) == "access denied: insufficient_role"
