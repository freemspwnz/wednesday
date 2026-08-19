from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions import AggregateMappingError, DataIntegrityError, RepositoryError, UnexpectedDBError

T = TypeVar("T")

_ENTITY = "image_view"


async def guard_view(
    *,
    operation: str,
    run: Callable[[], Awaitable[T]],
    entity_id: UUID | None = None,
    integrity_message: str | None = None,
    mapping_message: str | None = None,
) -> T:
    """Map SQLAlchemy / mapping failures to app-layer errors for view repo."""
    try:
        return await run()
    except IntegrityError as exc:
        if integrity_message is None:
            raise
        raise DataIntegrityError(
            integrity_message,
            operation=operation,
            entity=_ENTITY,
            entity_id=entity_id,
        ) from exc
    except ValueError as exc:
        if mapping_message is None:
            raise
        raise AggregateMappingError(
            mapping_message,
            operation=operation,
            entity=_ENTITY,
        ) from exc
    except SQLAlchemyError as exc:
        raise RepositoryError(
            f"SQLAlchemy failed during {operation}.",
            operation=operation,
            entity=_ENTITY,
            entity_id=entity_id,
        ) from exc
    except Exception as exc:
        raise UnexpectedDBError(f"Unexpected error during {operation}.") from exc
