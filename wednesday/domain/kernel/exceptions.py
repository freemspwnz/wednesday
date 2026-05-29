"""Domain exceptions.

Hierarchy:
    DomainError
    ├── ValidationError
    ├── AccessDeniedError (code: str)
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
    """Access denied with a typed policy code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"access denied: {code}")


class InvalidStateTransitionError(DomainError):
    """Attempt to make an invalid state transition."""


class StaleWriteError(DomainError):
    """Command timestamp is older than aggregate clock."""

    def __init__(self, message: str = "stale write") -> None:
        super().__init__(message)
