import pytest

from domain.kernel import (
    AccessDeniedError,
    ContentNotFoundError,
    DomainError,
    GenerationLimitExceededError,
    InvalidStateTransitionError,
    UnsafeContentError,
    ValidationError,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc_cls",
    [
        DomainError,
        ValidationError,
        ContentNotFoundError,
        AccessDeniedError,
        GenerationLimitExceededError,
        UnsafeContentError,
        InvalidStateTransitionError,
    ],
)
def test_kernel_exceptions_preserve_message(exc_cls: type[DomainError]) -> None:
    exc = exc_cls("problem")
    assert exc.message == "problem"
    assert str(exc) == "problem"
