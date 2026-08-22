from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.chat import ChatId
from domain.image import ImageId, ViewRepo
from domain.kernel.vo import AwareDatetime

from ...models import ImageORM, ViewORM
from .._guard import guard_repo


class SQLAViewRepo(ViewRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def was_shown(self, chat_id: ChatId, image_id: ImageId) -> bool:
        async def _run() -> bool:
            stmt = select(
                exists().where(
                    ViewORM.chat_id == chat_id.value,
                    ViewORM.image_id == image_id.value,
                ),
            )
            result = await self._session.execute(stmt)
            return bool(result.scalar_one())

        return await guard_repo(
            operation="was_shown",
            entity="image_view",
            sqlalchemy_message="SQLAlchemy failed during was_shown.",
            unexpected_message="Unexpected error during was_shown.",
            run=_run,
        )

    async def mark_shown(
        self,
        chat_id: ChatId,
        image_id: ImageId,
        at: AwareDatetime,
    ) -> None:
        async def _run() -> None:
            await self._session.execute(
                insert(ViewORM)
                .values(
                    chat_id=chat_id.value,
                    image_id=image_id.value,
                    shown_at=at.value,
                )
                .on_conflict_do_nothing(
                    index_elements=[ViewORM.chat_id, ViewORM.image_id],
                ),
            )

        await guard_repo(
            operation="mark_shown",
            entity="image_view",
            entity_id=image_id.value,
            integrity_message="Image view mark violated database constraints.",
            sqlalchemy_message="SQLAlchemy failed during mark_shown.",
            unexpected_message="Unexpected error during mark_shown.",
            run=_run,
        )

    async def get_unseen_for_chat(
        self,
        chat_id: ChatId,
        min_rating: int,
    ) -> ImageId | None:
        async def _run() -> ImageId | None:
            seen_exists = (
                select(1)
                .where(
                    ViewORM.chat_id == chat_id.value,
                    ViewORM.image_id == ImageORM.id,
                )
                .exists()
            )
            stmt = (
                select(ImageORM.id)
                .where(
                    (ImageORM.likes - ImageORM.dislikes) >= min_rating,
                    ImageORM.state == "active",
                    ~seen_exists,
                )
                .order_by(func.random())
                .limit(1)
            )
            result = await self._session.execute(stmt)
            image_id = result.scalar_one_or_none()
            if image_id is None:
                return None
            return ImageId(image_id)

        return await guard_repo(
            operation="get_unseen_for_chat",
            entity="image_view",
            mapping_message="Failed to map unseen image id.",
            sqlalchemy_message="SQLAlchemy failed during get_unseen_for_chat.",
            unexpected_message="Unexpected error during get_unseen_for_chat.",
            run=_run,
        )

    async def reset_for_chat(self, chat_id: ChatId) -> int:
        async def _run() -> int:
            result = await self._session.execute(
                delete(ViewORM).where(ViewORM.chat_id == chat_id.value).returning(ViewORM.image_id),
            )
            return len(result.all())

        return await guard_repo(
            operation="reset_for_chat",
            entity="image_view",
            sqlalchemy_message="SQLAlchemy failed during reset_for_chat.",
            unexpected_message="Unexpected error during reset_for_chat.",
            run=_run,
        )
