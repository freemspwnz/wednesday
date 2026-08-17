from ..base import AppError, UnexpectedAppError


class DBError(AppError):
    """Base exception for database persistence errors."""


class RepositoryError(DBError):
    """Repository operation failed."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        entity: str,
        entity_id: object | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.entity = entity
        self.entity_id = entity_id


class DataIntegrityError(RepositoryError):
    """Constraint or integrity violation in persistence layer."""


class AggregateMappingError(RepositoryError):
    """Invalid persistence payload for domain aggregate reconstruction."""


class DBUnavailableError(DBError):
    """Database is not available."""


class UnexpectedDBError(UnexpectedAppError):
    """Unexpected database infrastructure error."""
