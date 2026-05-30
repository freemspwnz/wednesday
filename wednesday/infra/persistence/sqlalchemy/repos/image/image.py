from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    SQLAAggregateMappingError,
    SQLADataIntegrityError,
    SQLARepositoryError,
    UnexpectedSQLAError,
)
from domain.catalog import Model
from domain.image import (
    ActiveStatus,
    HiddenStatus,
    Image,
    ImageId,
    ImageMeta,
    ImagePrompts,
    ImageRepo,
    TelegramFileId,
)
from domain.image.vo.states import HiddenReason
from domain.kernel.vo import AwareDatetime

from ...models import ImageORM, ImageSeenORM


class SQLAImageRepo(ImageRepo):
    """Image catalog repository backed by SQLAlchemy AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, image_id: ImageId) -> Image | None:
        try:
            stmt = select(ImageORM).where(ImageORM.id == image_id.value)
            result = await self._session.execute(stmt)
            orm_image = result.scalar_one_or_none()
            if orm_image is None:
                return None
            return _image_from_orm(orm_image)
        except ValueError as exc:
            raise SQLAAggregateMappingError(
                "Failed to map ORM image aggregate.",
                operation="get_by_id",
                entity="image",
                entity_id=image_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to load image aggregate.",
                operation="get_by_id",
                entity="image",
                entity_id=image_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while reading image aggregate.") from exc

    async def save(self, image: Image) -> None:
        try:
            status, hidden_reason = _status_to_orm(image)
            user_prompt, enriched_prompt = _prompts_to_orm(image.prompts)
            await self._session.execute(
                insert(ImageORM)
                .values(
                    id=image.id.value,
                    author_id=image.meta.author_id,
                    model=str(image.meta.model),
                    score=image.score,
                    status=status,
                    hidden_reason=hidden_reason,
                    created_at=image.created_at.value,
                    user_prompt=user_prompt,
                    enriched_prompt=enriched_prompt,
                    telegram_file_id=str(image.file_id) if image.file_id is not None else None,
                )
                .on_conflict_do_update(
                    index_elements=[ImageORM.id],
                    set_={
                        "author_id": image.meta.author_id,
                        "model": str(image.meta.model),
                        "score": image.score,
                        "status": status,
                        "hidden_reason": hidden_reason,
                        "user_prompt": user_prompt,
                        "enriched_prompt": enriched_prompt,
                        "telegram_file_id": str(image.file_id) if image.file_id is not None else None,
                    },
                )
            )
        except IntegrityError as exc:
            raise SQLADataIntegrityError(
                "Image save violated database constraints.",
                operation="save",
                entity="image",
                entity_id=image.id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to persist image aggregate.",
                operation="save",
                entity="image",
                entity_id=image.id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while saving image aggregate.") from exc

    async def exists_by_telegram_file_id(self, file_id: TelegramFileId) -> bool:
        try:
            stmt = select(exists().where(ImageORM.telegram_file_id == str(file_id)))
            result = await self._session.execute(stmt)
            return bool(result.scalar_one())
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to check image file id existence.",
                operation="exists_by_telegram_file_id",
                entity="image",
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while checking image file id existence.") from exc

    async def get_by_telegram_file_id(self, file_id: TelegramFileId) -> Image | None:
        try:
            stmt = select(ImageORM).where(ImageORM.telegram_file_id == str(file_id))
            result = await self._session.execute(stmt)
            orm_image = result.scalar_one_or_none()
            if orm_image is None:
                return None
            return _image_from_orm(orm_image)
        except ValueError as exc:
            raise SQLAAggregateMappingError(
                "Failed to map ORM image aggregate.",
                operation="get_by_telegram_file_id",
                entity="image",
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to load image by telegram file id.",
                operation="get_by_telegram_file_id",
                entity="image",
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while loading image by telegram file id.") from exc

    async def get_random_unseen_for_chat(
        self,
        chat_id: UUID,
        *,
        min_score: int,
    ) -> Image | None:
        try:
            seen_exists = (
                select(1)
                .where(
                    ImageSeenORM.chat_id == chat_id,
                    ImageSeenORM.image_id == ImageORM.id,
                )
                .exists()
            )
            stmt = (
                select(ImageORM)
                .where(
                    ImageORM.score > min_score - 1,
                    ImageORM.status == "active",
                    ~seen_exists,
                )
                .order_by(func.random())
                .limit(1)
            )
            result = await self._session.execute(stmt)
            orm_image = result.scalar_one_or_none()
            if orm_image is None:
                return None
            return _image_from_orm(orm_image)
        except ValueError as exc:
            raise SQLAAggregateMappingError(
                "Failed to map ORM image aggregate.",
                operation="get_random_unseen_for_chat",
                entity="image",
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to pick random unseen image.",
                operation="get_random_unseen_for_chat",
                entity="image",
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while picking random unseen image.") from exc


def _status_to_orm(image: Image) -> tuple[str, str | None]:
    if isinstance(image.status, ActiveStatus):
        return "active", None
    if isinstance(image.status, HiddenStatus):
        return "hidden", image.status.reason.value
    raise ValueError(f"Unknown image status: {image.status!r}")


def _status_from_orm(*, status: str, hidden_reason: str | None) -> ActiveStatus | HiddenStatus:
    if status == "active":
        return ActiveStatus()
    if status == "hidden" and hidden_reason is not None:
        return HiddenStatus(reason=HiddenReason(hidden_reason))
    raise ValueError(f"Inconsistent image status in ORM: status={status!r}, hidden_reason={hidden_reason!r}")


def _prompts_to_orm(prompts: ImagePrompts | None) -> tuple[str | None, str | None]:
    if prompts is None:
        return None, None
    return (
        str(prompts.user) if prompts.user is not None else None,
        str(prompts.enriched) if prompts.enriched is not None else None,
    )


def _prompts_from_orm(*, user_prompt: str | None, enriched_prompt: str | None) -> ImagePrompts | None:
    if user_prompt is None and enriched_prompt is None:
        return None
    return ImagePrompts.parse(user=user_prompt, enriched=enriched_prompt)


def _image_from_orm(orm: ImageORM) -> Image:
    meta = ImageMeta.create(author_id=orm.author_id, model=Model.parse(orm.model))
    prompts = _prompts_from_orm(user_prompt=orm.user_prompt, enriched_prompt=orm.enriched_prompt)
    file_id = TelegramFileId.parse(orm.telegram_file_id) if orm.telegram_file_id is not None else None
    return Image.restore(
        id=ImageId(orm.id),
        meta=meta,
        created_at=AwareDatetime.from_datetime(orm.created_at),
        score=orm.score,
        status=_status_from_orm(status=orm.status, hidden_reason=orm.hidden_reason),
        prompts=prompts,
        file_id=file_id,
    )
