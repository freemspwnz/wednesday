from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import DataIntegrityError, RepositoryError, UnexpectedDBError
from domain.image import ImageId, VoteRepo
from domain.image.vote import Vote

from ...models import VoteORM


class SQLAVoteRepo(VoteRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, image_id: ImageId, voter_id: UUID) -> Vote | None:
        try:
            stmt = select(VoteORM).where(
                VoteORM.image_id == image_id.value,
                VoteORM.voter_id == voter_id,
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return Vote(image_id=image_id, voter_id=voter_id, value=row.value)
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to load image vote.",
                operation="get",
                entity="image_vote",
                entity_id=image_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while loading image vote.") from exc

    async def upsert(self, vote: Vote) -> None:
        try:
            await self._session.execute(
                insert(VoteORM)
                .values(
                    image_id=vote.image_id.value,
                    voter_id=vote.voter_id,
                    value=vote.value,
                )
                .on_conflict_do_update(
                    index_elements=[VoteORM.image_id, VoteORM.voter_id],
                    set_={"value": vote.value},
                )
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Image vote save violated database constraints.",
                operation="upsert",
                entity="image_vote",
                entity_id=vote.image_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to persist image vote.",
                operation="upsert",
                entity="image_vote",
                entity_id=vote.image_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while saving image vote.") from exc

    async def list_for_image(self, image_id: ImageId) -> list[Vote]:
        try:
            stmt = select(VoteORM).where(VoteORM.image_id == image_id.value)
            result = await self._session.execute(stmt)
            rows = result.scalars().all()
            return [Vote(image_id=image_id, voter_id=row.voter_id, value=row.value) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to list image votes.",
                operation="list_for_image",
                entity="image_vote",
                entity_id=image_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while listing image votes.") from exc

    async def reset(self, image_id: ImageId) -> None:
        try:
            await self._session.execute(
                delete(VoteORM).where(VoteORM.image_id == image_id.value),
            )
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to reset image votes.",
                operation="reset",
                entity="image_vote",
                entity_id=image_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while resetting image votes.") from exc
