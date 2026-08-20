from datetime import datetime
from uuid import UUID

from app.dto import ImageCard
from domain.chat import ChatId
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
        image_id: str,
        voter_id: str,
        chat_id: str,
        value: int,
        at: datetime,
    ) -> ImageCard | None:
        """Record a vote and mark the image seen for the voter's private chat."""
        self._logger.debug(
            "Image vote scenario started",
            image_id=image_id,
            voter_id=voter_id,
            chat_id=chat_id,
            value=value,
        )
        time = AwareDatetime.from_datetime(at)
        i_id = ImageId(UUID(image_id))
        v_id = UserId(UUID(voter_id))
        c_id = ChatId(UUID(chat_id))
        async with self._uow:
            existing = await self._get_vote_if_exists(
                image_id=i_id,
                voter_id=v_id,
            )
            old = existing.value if existing is not None else None

            if old == value:
                await self._uow.views.mark_shown(c_id, i_id, at=time)
                return None

            image = await self._load_image_or_raise(image_id=i_id)
            image.add_vote(new=value, old=old, at=time)
            self._apply_rating_visibility(image=image, at=time)
            await self._uow.images.save(image)

            vote = Vote(image_id=i_id, voter_id=v_id, value=value)
            if existing is None:
                await self._uow.votes.upsert(vote)
            else:
                await self._uow.votes.upsert(existing.change(vote.value))
            await self._uow.views.mark_shown(c_id, i_id, at=time)

        self._logger.info(
            "Image aggregate updated",
            action="vote",
            image_id=image_id,
            voter_id=voter_id,
            chat_id=chat_id,
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
