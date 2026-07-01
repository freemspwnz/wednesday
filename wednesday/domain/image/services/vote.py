from __future__ import annotations

from uuid import UUID

from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

from ..exceptions import ImageNotFoundError, ValidationError
from ..image import Image
from ..policies import ImageScorePolicy
from ..protocols import ImageRepo, VoteRepo
from ..vo import ActiveState, HiddenReason, HiddenState, ImageId
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
        vote_repo: VoteRepo,
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
        ImageVoteService._apply_score_visibility(image, at=at)
        await image_repo.save(image)
        return image

    @staticmethod
    def _apply_score_visibility(image: Image, *, at: AwareDatetime) -> None:
        if isinstance(image.state, HiddenState) and image.state.reason == HiddenReason.ADMIN:
            return

        if ImageScorePolicy.is_selectable(image.score):
            if isinstance(image.state, HiddenState):
                image.show(actor=UserRole.SYSTEM, at=at)
        elif image.score <= 0 and isinstance(image.state, ActiveState):
            image.hide(actor=UserRole.SYSTEM, reason=HiddenReason.SCORE, at=at)
