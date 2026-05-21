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
        AccessDeniedError,
        InvalidStateTransitionError,
    ],
)
def test_kernel_exceptions_preserve_message(exc_cls: type[DomainError]) -> None:
    exc = exc_cls("problem")
    assert exc.message == "problem"
    assert str(exc) == "problem"
