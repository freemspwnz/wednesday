"""Domain exceptions.

Hierarchy:
    DomainError
    ├── ValidationError
    ├── AccessDeniedError
    ├── InvalidStateTransitionError
    └── StaleWriteError
"""


class DomainError(Exception):
    """Base domain exception with a human-readable message."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class ValidationError(DomainError):
    """Data does not comply with business rules."""


class AccessDeniedError(DomainError):
    """Access denied."""


class InvalidStateTransitionError(DomainError):
    """Attempt to make an invalid state transition."""


class StaleWriteError(DomainError):
    """Command timestamp is older than aggregate clock."""

    def __init__(self, message: str = "stale write") -> None:
        super().__init__(message)
