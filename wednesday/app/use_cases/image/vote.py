from uuid import UUID

from domain.image import Image, ImageId, ImageVoteService
from domain.kernel.vo import AwareDatetime

from .base import ImageBaseUseCase


class ImageVoteUseCase(ImageBaseUseCase):
    """Catalog vote use case methods."""

    async def vote(
        self,
        *,
        image_id: ImageId,
        voter_id: UUID,
        value: int,
        at: AwareDatetime,
    ) -> Image:
        self._logger.debug(
            "Image vote scenario started",
            image_id=str(image_id.value),
            voter_id=str(voter_id),
            value=value,
        )
        async with self._uow:
            image = await ImageVoteService.vote(
                image_id=image_id,
                voter_id=voter_id,
                value=value,
                image_repo=self._uow.images,
                vote_repo=self._uow.votes,
                at=at,
            )
        self._logger.info(
            "Image aggregate updated",
            action="vote",
            image_id=str(image.id.value),
            voter_id=str(voter_id),
            value=value,
        )
        return image
