from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import DataIntegrityError, RepositoryError, UnexpectedDBError
from domain.image import ImageId, ViewRepo
from domain.kernel.vo import AwareDatetime

from ...models import ViewORM


class SQLAViewRepo(ViewRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def was_shown(self, chat_id: UUID, image_id: ImageId) -> bool:
        try:
            stmt = select(
                exists().where(
                    ViewORM.chat_id == chat_id,
                    ViewORM.image_id == image_id.value,
                )
            )
            result = await self._session.execute(stmt)
            return bool(result.scalar_one())
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to check image view status.",
                operation="was_shown",
                entity="image_view",
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while checking image view status.") from exc

    async def mark_shown(
        self,
        chat_id: UUID,
        image_id: ImageId,
        at: AwareDatetime,
    ) -> None:
        try:
            await self._session.execute(
                insert(ViewORM)
                .values(
                    chat_id=chat_id,
                    image_id=image_id.value,
                    shown_at=at.value,
                )
                .on_conflict_do_nothing(
                    index_elements=[ViewORM.chat_id, ViewORM.image_id],
                )
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Image view mark violated database constraints.",
                operation="mark_shown",
                entity="image_view",
                entity_id=image_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to mark image as shown.",
                operation="mark_shown",
                entity="image_view",
                entity_id=image_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while marking image as shown.") from exc
