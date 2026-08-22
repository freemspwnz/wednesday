from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.image import ImageId, Vote, VoteRepo
from domain.user import UserId

from ...models import VoteORM
from .._guard import guard_repo


class SQLAVoteRepo(VoteRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, image_id: ImageId, voter_id: UserId) -> Vote | None:
        async def _run() -> Vote | None:
            stmt = select(VoteORM).where(
                VoteORM.image_id == image_id.value,
                VoteORM.voter_id == voter_id.value,
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return Vote(image_id=image_id, voter_id=voter_id, value=row.value)

        return await guard_repo(
            operation="get",
            entity="image_vote",
            entity_id=image_id.value,
            sqlalchemy_message="SQLAlchemy failed to load image vote.",
            unexpected_message="Unexpected error while loading image vote.",
            run=_run,
        )

    async def upsert(self, vote: Vote) -> None:
        async def _run() -> None:
            await self._session.execute(
                insert(VoteORM)
                .values(
                    image_id=vote.image_id.value,
                    voter_id=vote.voter_id.value,
                    value=vote.value,
                )
                .on_conflict_do_update(
                    index_elements=[VoteORM.image_id, VoteORM.voter_id],
                    set_={"value": vote.value},
                ),
            )

        return await guard_repo(
            operation="upsert",
            entity="image_vote",
            entity_id=vote.image_id.value,
            sqlalchemy_message="SQLAlchemy failed to persist image vote.",
            unexpected_message="Unexpected error while saving image vote.",
            integrity_message="Image vote save violated database constraints.",
            run=_run,
        )

    async def list_for_image(self, image_id: ImageId) -> list[Vote]:
        async def _run() -> list[Vote]:
            stmt = select(VoteORM).where(VoteORM.image_id == image_id.value)
            result = await self._session.execute(stmt)
            rows = result.scalars().all()
            return [Vote(image_id=image_id, voter_id=UserId(row.voter_id), value=row.value) for row in rows]

        return await guard_repo(
            operation="list_for_image",
            entity="image_vote",
            entity_id=image_id.value,
            sqlalchemy_message="SQLAlchemy failed to list image votes.",
            unexpected_message="Unexpected error while listing image votes.",
            run=_run,
        )

    async def reset(self, image_id: ImageId) -> None:
        async def _run() -> None:
            await self._session.execute(
                delete(VoteORM).where(VoteORM.image_id == image_id.value),
            )

        return await guard_repo(
            operation="reset",
            entity="image_vote",
            entity_id=image_id.value,
            sqlalchemy_message="SQLAlchemy failed to reset image votes.",
            unexpected_message="Unexpected error while resetting image votes.",
            run=_run,
        )
