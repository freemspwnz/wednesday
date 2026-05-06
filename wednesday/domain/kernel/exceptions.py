"""Domain exceptions.

Hierarchy:
    DomainError
    ├── ValidationError
    ├── AccessDeniedError
    └── InvalidStateTransitionError
"""


class DomainError(Exception):
    """Base domain exception with a human-readable message."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


# ── Data Validation Errors ──


class ValidationError(DomainError):
    """Data does not comply with business rules."""


# ── Access Denied Errors ──


class AccessDeniedError(DomainError):
    """Access denied."""


# ── Policy Violation Errors ──


class InvalidStateTransitionError(DomainError):
    """Attempt to make an invalid state transition."""
