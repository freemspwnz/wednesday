from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AggregateMappingError, DataIntegrityError, RepositoryError, UnexpectedDBError
from domain.chat import ChatId
from domain.image import ImageId, ViewRepo
from domain.kernel.vo import AwareDatetime

from ...models import ImageORM, ViewORM


class SQLAViewRepo(ViewRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def was_shown(self, chat_id: ChatId, image_id: ImageId) -> bool:
        try:
            chat_id = ChatId.ensure(chat_id)
            stmt = select(
                exists().where(
                    ViewORM.chat_id == chat_id.value,
                    ViewORM.image_id == image_id.value,
                ),
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
        chat_id: ChatId,
        image_id: ImageId,
        at: AwareDatetime,
    ) -> None:
        try:
            chat_id = ChatId.ensure(chat_id)
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

    async def get_unseen_for_chat(
        self,
        chat_id: ChatId,
        min_rating: int,
    ) -> ImageId | None:
        try:
            chat_id = ChatId.ensure(chat_id)
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
        except ValueError as exc:
            raise AggregateMappingError(
                "Failed to map unseen image id.",
                operation="get_unseen_for_chat",
                entity="image_view",
            ) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to pick unseen image for chat.",
                operation="get_unseen_for_chat",
                entity="image_view",
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while picking unseen image for chat.") from exc

    async def reset_for_chat(self, chat_id: ChatId) -> int:
        try:
            chat_id = ChatId.ensure(chat_id)
            result = await self._session.execute(
                delete(ViewORM).where(ViewORM.chat_id == chat_id.value).returning(ViewORM.image_id),
            )
            return len(result.all())
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "SQLAlchemy failed to reset image view history for chat.",
                operation="reset_for_chat",
                entity="image_view",
            ) from exc
        except Exception as exc:
            raise UnexpectedDBError("Unexpected error while resetting image view history for chat.") from exc
