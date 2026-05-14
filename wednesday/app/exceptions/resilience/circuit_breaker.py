from ..base import AppError, UnexpectedAppError


class CircuitError(AppError):
    """Base circuit breaker error."""


class CircuitOpenError(CircuitError):
    """Raised when circuit breaker is OPEN."""

    def __init__(
        self,
        message: str,
        retry_after: float,
    ) -> None:
        super().__init__(message)

        self.retry_after = retry_after


class CircuitStateChangeError(CircuitError):
    """Raised when circuit breaker state cannot be changed."""


class UnexpectedCircuitError(UnexpectedAppError):
    """Unexpected circuit breaker error."""
