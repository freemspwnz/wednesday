from __future__ import annotations

from uuid import UUID

from domain.kernel.vo import AwareDatetime

from ..exceptions import ImageNotFoundError, ValidationError
from ..image import Image
from ..protocols import ImageRepo, ImageVoteRepo
from ..vo import ImageId
from ..vote import Vote


class ImageVoteService:
    """Upsert vote and recalculate catalog image score."""

    @staticmethod
    async def vote(  # noqa: PLR0913
        *,
        image_id: ImageId,
        voter_id: UUID,
        value: int,
        image_repo: ImageRepo,
        vote_repo: ImageVoteRepo,
        at: AwareDatetime,
    ) -> Image:
        image_id = ImageId.ensure(image_id)
        at = AwareDatetime.ensure(at)
        if not isinstance(voter_id, UUID):
            raise ValidationError("voter_id must be a UUID")

        image = await image_repo.get_by_id(image_id)
        if image is None:
            raise ImageNotFoundError(str(image_id))

        existing = await vote_repo.get(image_id, voter_id)
        if existing is None:
            await vote_repo.upsert(Vote(image_id=image_id, voter_id=voter_id, value=value))
        elif existing.value != value:
            await vote_repo.upsert(existing.change(value))
        else:
            return image

        votes = await vote_repo.list_for_image(image_id)
        image.recalculate_score([vote.value for vote in votes], at=at)
        await image_repo.save(image)
        return image
