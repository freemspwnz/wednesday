from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from domain.catalog import Model
from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    Image,
    ImageId,
    ImageMeta,
    ImagePrompts,
    NormalizedPrompt,
    PromptSource,
    TelegramFileId,
    TextGenError,
)
from domain.image.protocols import (
    ImageGenerator,
    ImageRepo,
    PromptCatalog,
    PromptComponents,
    TextGenerator,
    ViewRepo,
    VoteRepo,
)
from domain.image.vote import Vote
from domain.kernel.vo import AwareDatetime


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def mk_file_id(value: str = "AgACAgIAAxkBAAI") -> TelegramFileId:
    return TelegramFileId.parse(value)


def mk_meta(*, author_id: int = 1, model: str = "gigachat-2-lite") -> ImageMeta:
    return ImageMeta(author_id=UUID(int=author_id), model=Model.parse(model))


def mk_prompts(
    *,
    primary: str = "frog meme",
    source: PromptSource = PromptSource.USER,
    enriched: str | None = "enriched frog",
) -> ImagePrompts:
    return ImagePrompts(
        primary=NormalizedPrompt.parse(primary),
        source=source,
        enriched=NormalizedPrompt.parse(enriched) if enriched is not None else None,
    )


def mk_components() -> PromptComponents:
    return PromptComponents(
        heroes=("Wednesday frog",),
        colors=("green",),
        styles=("meme",),
        professions=("coder",),
        actions=("coding",),
        places=("swamp",),
        portraits=("portrait",),
    )


def mk_image(  # noqa: PLR0913
    *,
    image_id: int = 1,
    model: str = "gigachat-2-lite",
    author_id: int = 1,
    created_at: AwareDatetime | None = None,
    score: int | None = None,
    file_id: TelegramFileId | None = None,
    prompts: ImagePrompts | None = None,
    state: HiddenState | ActiveState | None = None,
) -> Image:
    current = created_at or dt(12)
    resolved_file_id = file_id or mk_file_id()
    resolved_prompts = prompts or mk_prompts()
    meta = mk_meta(author_id=author_id, model=model)
    image_id_vo = ImageId(UUID(int=image_id))

    if score is None:
        return Image.register(
            id=image_id_vo,
            meta=meta,
            file_id=resolved_file_id,
            prompts=resolved_prompts,
            created_at=current,
        )

    resolved_state = state or (ActiveState() if score > 0 else HiddenState(reason=HiddenReason.SCORE))
    return Image.restore(
        id=image_id_vo,
        meta=meta,
        created_at=current,
        score=score,
        state=resolved_state,
        file_id=resolved_file_id,
        prompts=resolved_prompts,
    )


@dataclass
class FakeImageRepo(ImageRepo):
    images: dict[ImageId, Image] = field(default_factory=dict)
    save_calls: int = 0

    async def get_by_id(self, image_id: ImageId) -> Image | None:
        return self.images.get(ImageId.ensure(image_id))

    async def save(self, image: Image) -> None:
        entity = Image.ensure(image)
        self.images[entity.id] = entity
        self.save_calls += 1

    async def exists_by_telegram_file_id(self, file_id: TelegramFileId) -> bool:
        file_id = TelegramFileId.ensure(file_id)
        return any(image.file_id == file_id for image in self.images.values())

    async def get_by_telegram_file_id(self, file_id: TelegramFileId) -> Image | None:
        file_id = TelegramFileId.ensure(file_id)
        for image in self.images.values():
            if image.file_id == file_id:
                return image
        return None

    async def get_random_unseen_for_chat(self, chat_id: UUID, *, min_score: int) -> Image | None:
        _ = chat_id
        candidates = [
            image
            for image in self.images.values()
            if image.score > min_score - 1 and isinstance(image.state, ActiveState)
        ]
        return candidates[0] if candidates else None

    @classmethod
    def with_images(cls, *images: Image) -> Self:
        repo = cls()
        for image in images:
            repo.images[image.id] = image
        return repo


@dataclass
class FakeViewRepo(ViewRepo):
    shown: set[tuple[UUID, ImageId]] = field(default_factory=set)

    async def was_shown(self, chat_id: UUID, image_id: ImageId) -> bool:
        return (chat_id, ImageId.ensure(image_id)) in self.shown

    async def mark_shown(self, chat_id: UUID, image_id: ImageId, at: AwareDatetime) -> None:
        _ = at
        self.shown.add((chat_id, ImageId.ensure(image_id)))


@dataclass
class FakeImageVoteRepo(VoteRepo):
    votes: dict[tuple[ImageId, UUID], Vote] = field(default_factory=dict)

    async def get(self, image_id: ImageId, voter_id: UUID) -> Vote | None:
        return self.votes.get((ImageId.ensure(image_id), voter_id))

    async def upsert(self, vote: Vote) -> None:
        self.votes[vote.image_id, vote.voter_id] = vote

    async def list_for_image(self, image_id: ImageId) -> list[Vote]:
        image_id = ImageId.ensure(image_id)
        return [vote for (stored_id, _), vote in self.votes.items() if stored_id == image_id]

    async def reset(self, image_id: ImageId) -> None:
        image_id = ImageId.ensure(image_id)
        self.votes = {key: vote for key, vote in self.votes.items() if key[0] != image_id}


class FakePromptCatalog(PromptCatalog):
    def __init__(
        self,
        *,
        components_data: PromptComponents | None = None,
        enrichment_system: str = "enrich-system",
        generation_system: str = "gen-system",
        base_system: str = "base-system",
    ) -> None:
        self.components_data = components_data or mk_components()
        self.enrichment_system = enrichment_system
        self.generation_system = generation_system
        self.base_system = base_system

    async def enrichment_prompt(self) -> str:
        return self.enrichment_system

    async def generation_prompt(self) -> str:
        return self.generation_system

    async def base_prompt(self) -> str:
        return self.base_system

    async def components(self) -> PromptComponents:
        return self.components_data


@dataclass
class FakeTextGenerator(TextGenerator):
    response: str = "llm prompt"
    fail: bool = False

    async def generate_text(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        _ = model
        _ = system_prompt
        _ = user_prompt
        if self.fail:
            raise TextGenError("text generator unavailable")
        return self.response


@dataclass
class FakeImageGenerator(ImageGenerator):
    content: bytes = b"png-bytes"

    async def generate_image(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> bytes:
        _ = model
        _ = system_prompt
        _ = user_prompt
        return self.content
