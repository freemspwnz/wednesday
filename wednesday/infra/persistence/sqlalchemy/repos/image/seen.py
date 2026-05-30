from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SQLADataIntegrityError, SQLARepositoryError, UnexpectedSQLAError
from domain.image import ImageId, ImageSeenRepo
from domain.kernel.vo import AwareDatetime

from ...models import ImageSeenORM


class SQLAImageSeenRepo(ImageSeenRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_seen(self, chat_id: UUID, image_id: ImageId) -> bool:
        try:
            stmt = select(
                exists().where(
                    ImageSeenORM.chat_id == chat_id,
                    ImageSeenORM.image_id == image_id.value,
                )
            )
            result = await self._session.execute(stmt)
            return bool(result.scalar_one())
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to check image seen status.",
                operation="is_seen",
                entity="image_seen",
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while checking image seen status.") from exc

    async def mark_seen(
        self,
        chat_id: UUID,
        image_id: ImageId,
        at: AwareDatetime,
    ) -> None:
        try:
            await self._session.execute(
                insert(ImageSeenORM)
                .values(
                    chat_id=chat_id,
                    image_id=image_id.value,
                    seen_at=at.value,
                )
                .on_conflict_do_nothing(
                    index_elements=[ImageSeenORM.chat_id, ImageSeenORM.image_id],
                )
            )
        except IntegrityError as exc:
            raise SQLADataIntegrityError(
                "Image seen mark violated database constraints.",
                operation="mark_seen",
                entity="image_seen",
                entity_id=image_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to mark image as seen.",
                operation="mark_seen",
                entity="image_seen",
                entity_id=image_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while marking image as seen.") from exc
