from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.catalog import Model
from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    Image,
    ImageId,
    ImageMeta,
    ImagePrompts,
    ImageRating,
    ImageRepo,
    NormalizedPrompt,
    PromptSource,
    TelegramFileId,
)
from domain.kernel.vo import AwareDatetime
from domain.user import UserId

from ...models import ImageORM
from .._guard import guard_repo


class SQLAImageRepo(ImageRepo):
    """Image catalog repository backed by SQLAlchemy AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, image_id: ImageId) -> Image | None:
        async def _run() -> Image | None:
            stmt = select(ImageORM).where(ImageORM.id == image_id.value)
            result = await self._session.execute(stmt)
            orm_image = result.scalar_one_or_none()
            if orm_image is None:
                return None
            return _image_from_orm(orm_image)

        return await guard_repo(
            operation="get_by_id",
            entity="image",
            entity_id=image_id.value,
            mapping_message="Failed to map ORM image aggregate.",
            sqlalchemy_message="SQLAlchemy failed to load image aggregate.",
            unexpected_message="Unexpected error while reading image aggregate.",
            run=_run,
        )

    async def save(self, image: Image) -> None:
        async def _run() -> None:
            state_value, hidden_reason = _state_to_orm(image)
            primary_prompt, enriched_prompt, prompt_source = _prompts_to_orm(image.prompts)
            await self._session.execute(
                insert(ImageORM)
                .values(
                    id=image.id.value,
                    author_id=image.meta.author_id.value,
                    model=str(image.meta.model),
                    likes=image.rating.likes,
                    dislikes=image.rating.dislikes,
                    state=state_value,
                    hidden_reason=hidden_reason,
                    created_at=image.created_at.value,
                    primary_prompt=primary_prompt,
                    enriched_prompt=enriched_prompt,
                    prompt_source=prompt_source,
                    telegram_file_id=str(image.file_id),
                )
                .on_conflict_do_update(
                    index_elements=[ImageORM.id],
                    set_={
                        "author_id": image.meta.author_id.value,
                        "model": str(image.meta.model),
                        "likes": image.rating.likes,
                        "dislikes": image.rating.dislikes,
                        "state": state_value,
                        "hidden_reason": hidden_reason,
                        "primary_prompt": primary_prompt,
                        "enriched_prompt": enriched_prompt,
                        "prompt_source": prompt_source,
                        "telegram_file_id": str(image.file_id),
                    },
                ),
            )

        await guard_repo(
            operation="save",
            entity="image",
            entity_id=image.id.value,
            integrity_message="Image save violated database constraints.",
            sqlalchemy_message="SQLAlchemy failed to persist image aggregate.",
            unexpected_message="Unexpected error while saving image aggregate.",
            run=_run,
        )

    async def exists_by_telegram_file_id(self, file_id: TelegramFileId) -> bool:
        async def _run() -> bool:
            stmt = select(exists().where(ImageORM.telegram_file_id == str(file_id)))
            result = await self._session.execute(stmt)
            return bool(result.scalar_one())

        return await guard_repo(
            operation="exists_by_telegram_file_id",
            entity="image",
            sqlalchemy_message="SQLAlchemy failed to check image file id existence.",
            unexpected_message="Unexpected error while checking image file id existence.",
            run=_run,
        )

    async def get_by_telegram_file_id(self, file_id: TelegramFileId) -> Image | None:
        async def _run() -> Image | None:
            stmt = select(ImageORM).where(ImageORM.telegram_file_id == str(file_id))
            result = await self._session.execute(stmt)
            orm_image = result.scalar_one_or_none()
            if orm_image is None:
                return None
            return _image_from_orm(orm_image)

        return await guard_repo(
            operation="get_by_telegram_file_id",
            entity="image",
            mapping_message="Failed to map ORM image aggregate.",
            sqlalchemy_message="SQLAlchemy failed to load image by telegram file id.",
            unexpected_message="Unexpected error while loading image by telegram file id.",
            run=_run,
        )


def _state_to_orm(image: Image) -> tuple[str, str | None]:
    if isinstance(image.state, ActiveState):
        return "active", None
    if isinstance(image.state, HiddenState):
        return "hidden", image.state.reason.value
    raise ValueError(f"Unknown image state: {image.state!r}")


def _state_from_orm(*, state: str, hidden_reason: str | None) -> ActiveState | HiddenState:
    if state == "active":
        return ActiveState()
    if state == "hidden" and hidden_reason is not None:
        return HiddenState(reason=HiddenReason(hidden_reason))
    raise ValueError(f"Inconsistent image state in ORM: state={state!r}, hidden_reason={hidden_reason!r}")


def _prompts_to_orm(prompts: ImagePrompts) -> tuple[str, str | None, str]:
    enriched = str(prompts.enriched) if prompts.enriched is not None else None
    return str(prompts.primary), enriched, prompts.source.value


def _prompts_from_orm(
    *,
    primary_prompt: str,
    enriched_prompt: str | None,
    prompt_source: str,
) -> ImagePrompts:
    return ImagePrompts(
        primary=NormalizedPrompt.parse(primary_prompt),
        source=PromptSource(prompt_source),
        enriched=NormalizedPrompt.parse(enriched_prompt) if enriched_prompt is not None else None,
    )


def _image_from_orm(orm: ImageORM) -> Image:
    meta = ImageMeta(author_id=UserId(orm.author_id), model=Model.parse(orm.model))
    prompts = _prompts_from_orm(
        primary_prompt=orm.primary_prompt,
        enriched_prompt=orm.enriched_prompt,
        prompt_source=orm.prompt_source,
    )
    return Image.restore(
        id=ImageId(orm.id),
        meta=meta,
        created_at=AwareDatetime.from_datetime(orm.created_at),
        rating=ImageRating(likes=orm.likes, dislikes=orm.dislikes),
        state=_state_from_orm(state=orm.state, hidden_reason=orm.hidden_reason),
        prompts=prompts,
        file_id=TelegramFileId.parse(orm.telegram_file_id),
    )
