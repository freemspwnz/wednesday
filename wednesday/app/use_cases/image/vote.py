from app.dto import ImageCard
from domain.image import HiddenReason, Image, ImageId, ImageRatingPolicy, Vote
from domain.image.exceptions import ValidationError
from domain.image.policies import Hide, NoOperation, Show
from domain.kernel import AwareDatetime
from domain.user import UserId, UserRole

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
            existing = await self._get_vote_if_exists(image_id=image_id, voter_id=voter_id)
            old = existing.value if existing is not None else None

            if old == value:
                return None

            image = await self._load_image_or_raise(image_id=image_id)
            image.add_vote(new=value, old=old, at=at)
            self._apply_rating_visibility(image=image, at=at)
            await self._uow.images.save(image)

            vote = Vote(image_id=image_id, voter_id=voter_id, value=value)
            if existing is None:
                await self._uow.votes.upsert(vote)
            else:
                await self._uow.votes.upsert(existing.change(vote.value))

        self._logger.info(
            "Image aggregate updated",
            action="vote",
            image_id=str(image_id.value),
            voter_id=str(voter_id.value),
            value=value,
        )

        return ImageCard.from_domain(image)

    @staticmethod
    def _apply_rating_visibility(*, image: Image, at: AwareDatetime) -> None:
        match ImageRatingPolicy.evaluate(image.rating, image.state):
            case NoOperation():
                return
            case Hide():
                image.hide(actor=UserRole.SYSTEM, reason=HiddenReason.RATING, at=at)
            case Show():
                image.show(actor=UserRole.SYSTEM, at=at)
            case _:
                raise ValidationError("unknown decision")
