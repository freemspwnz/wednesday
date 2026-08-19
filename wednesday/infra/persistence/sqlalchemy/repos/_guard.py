from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions import DataIntegrityError, RepositoryError, UnexpectedDBError

T = TypeVar("T")


async def guard_repo(  # noqa: PLR0913
    *,
    operation: str,
    entity: str,
    entity_id: UUID,
    run: Callable[[], Awaitable[T]],
    sqlalchemy_message: str,
    unexpected_message: str,
    integrity_message: str | None = None,
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
    except SQLAlchemyError as exc:
        raise RepositoryError(
            sqlalchemy_message,
            operation=operation,
            entity=entity,
            entity_id=entity_id,
        ) from exc
    except Exception as exc:
        raise UnexpectedDBError(unexpected_message) from exc
