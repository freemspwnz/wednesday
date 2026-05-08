from ..base import AppError, UnexpectedAppError


class SQLAError(AppError):
    """Base exception for SQLAlchemy errors."""


class SQLARepositoryError(SQLAError):
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


class SQLADataIntegrityError(SQLARepositoryError):
    """Constraint or integrity violation in persistence layer."""


class SQLAAggregateMappingError(SQLARepositoryError):
    """Invalid ORM payload for domain aggregate reconstruction."""


class UnexpectedSQLAError(UnexpectedAppError):
    """Unexpected SQLAlchemy infrastructure error."""
