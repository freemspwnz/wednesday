from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions import (
    AggregateMappingError,
    DataIntegrityError,
    RepositoryError,
    UnexpectedDBError,
)

T = TypeVar("T")


async def guard_repo(  # noqa: PLR0913
    *,
    operation: str,
    entity: str,
    run: Callable[[], Awaitable[T]],
    sqlalchemy_message: str,
    unexpected_message: str,
    entity_id: UUID | None = None,
    integrity_message: str | None = None,
    mapping_message: str | None = None,
) -> T:
    """Map SQLAlchemy failures to app-layer repository errors."""
    try:
        return await run()
    except IntegrityError as exc:
        if integrity_message is None:
            raise
        raise DataIntegrityError(
            integrity_message,
            operation=operation,
            entity=entity,
            entity_id=entity_id,
        ) from exc
    except ValueError as exc:
        if mapping_message is None:
            raise
        raise AggregateMappingError(
            mapping_message,
            operation=operation,
            entity=entity,
            entity_id=entity_id,
        ) from exc
    except SQLAlchemyError as exc:
        raise RepositoryError(
            sqlalchemy_message,
            operation=operation,
            entity=entity,
            entity_id=entity_id,
        ) from exc
    except Exception as exc:
        raise UnexpectedDBError(unexpected_message) from exc
