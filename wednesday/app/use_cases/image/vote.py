from app.dto import ImageCard
from domain.image import (
    ImageId,
    ImageLifecycleService,
    ImageVoteService,
    Vote,
)
from domain.kernel import AwareDatetime
from domain.user import UserId

from .base import ImageBaseUseCase


class ImageVoteUseCase(ImageBaseUseCase):
    """Catalog vote use case methods."""

    async def vote(
        self,
        *,
        image_id: ImageId,
        voter_id: UserId,
        value: int,
        at: AwareDatetime,
    ) -> ImageCard | None:
        self._logger.debug(
            "Image vote scenario started",
            image_id=str(image_id.value),
            voter_id=str(voter_id.value),
            value=value,
        )
        async with self._uow:
            existing = await ImageVoteService.get_if_exists(
                image_id=image_id,
                voter_id=voter_id,
                repo=self._uow.votes,
            )
            old = existing.value if existing is not None else None

            if old == value:
                return None

            image = await ImageLifecycleService.apply_vote(
                image_id=image_id,
                new=value,
                old=old,
                repo=self._uow.images,
                at=at,
            )
            await ImageVoteService.vote(
                vote=Vote(image_id=image_id, voter_id=voter_id, value=value),
                repo=self._uow.votes,
            )

        self._logger.info(
            "Image aggregate updated",
            action="vote",
            image_id=str(image_id.value),
            voter_id=str(voter_id.value),
            value=value,
        )

        return ImageCard.from_domain(image)
