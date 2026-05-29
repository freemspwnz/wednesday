from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from domain.catalog import Model
from domain.image import ActiveStatus, HiddenStatus, Image, ImageId, ImageMeta, ImagePrompts, TelegramFileId
from domain.image.protocols import ImageRepo, ImageVoteRepo
from domain.image.vo.states import HiddenReason
from domain.image.vote import Vote
from domain.kernel.vo import AwareDatetime


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def mk_image(  # noqa: PLR0913
    *,
    image_id: int = 1,
    model: str = "gigachat-2-lite",
    author_id: int = 1,
    created_at: AwareDatetime | None = None,
    score: int | None = None,
    user_prompt: str | None = None,
    enriched_prompt: str | None = "enriched frog",
) -> Image:
    current = created_at or dt(12)
    prompts = ImagePrompts.parse(user=user_prompt, enriched=enriched_prompt) if user_prompt or enriched_prompt else None
    meta = ImageMeta.create(author_id=UUID(int=author_id), model=Model.parse(model))
    image_id_vo = ImageId(UUID(int=image_id))

    if score is None:
        return Image.register(
            id=image_id_vo,
            meta=meta,
            created_at=current,
            prompts=prompts,
        )

    status = ActiveStatus() if score > 0 else HiddenStatus(reason=HiddenReason.VOTES)
    return Image.restore(
        id=image_id_vo,
        meta=meta,
        created_at=current,
        score=score,
        status=status,
        prompts=prompts,
    )


@dataclass
class FakeImageRepo(ImageRepo):
    """In-memory ImageRepo for domain tests."""

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

    async def get_random_unseen_for_chat(
        self,
        chat_id: UUID,
        *,
        min_score: int,
    ) -> Image | None:
        _ = chat_id
        _ = min_score
        return None

    @classmethod
    def with_images(cls, *images: Image) -> FakeImageRepo:
        repo = cls()
        for image in images:
            repo.images[image.id] = image
        return repo


@dataclass
class FakeImageVoteRepo(ImageVoteRepo):
    """In-memory ImageVoteRepo for domain tests."""

    votes: dict[tuple[ImageId, UUID], Vote] = field(default_factory=dict)

    async def get(self, image_id: ImageId, voter_id: UUID) -> Vote | None:
        return self.votes.get((ImageId.ensure(image_id), voter_id))

    async def upsert(self, vote: Vote) -> None:
        self.votes[vote.image_id, vote.voter_id] = vote

    async def list_for_image(self, image_id: ImageId) -> list[Vote]:
        image_id = ImageId.ensure(image_id)
        return [vote for (stored_id, _), vote in self.votes.items() if stored_id == image_id]
