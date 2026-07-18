from uuid import UUID

from app.dto import ImageCard
from app.protocols import Logger
from domain.image import Image, ImageId, ImageRepo, ImageVoteService, ViewRepo, VoteRepo
from domain.kernel.vo import AwareDatetime

_MIN_SCORE = 1


class ImageCommandService:
    """Image catalog commands: random pick and voting."""

    def __init__(self, *, logger: Logger) -> None:
        self._logger = logger.bind(module=self.__class__.__name__)

    async def pick_for_chat(
        self,
        *,
        images: ImageRepo,
        views: ViewRepo,
        chat_id: UUID,
        at: AwareDatetime,
    ) -> ImageCard | None:
        image = await images.get_random_unseen_for_chat(chat_id, min_score=_MIN_SCORE)
        if image is None:
            self._logger.debug("No unseen images for chat", chat_id=str(chat_id))
            return None

        await views.mark_shown(chat_id, image.id, at=at)
        self._logger.debug(
            "Random image picked for chat",
            chat_id=str(chat_id),
            image_id=str(image.id.value),
        )
        return ImageCard.from_domain(image)

    async def vote(  # noqa: PLR0913
        self,
        *,
        image_id: ImageId,
        voter_id: UUID,
        value: int,
        image_repo: ImageRepo,
        vote_repo: VoteRepo,
        at: AwareDatetime,
    ) -> Image:
        image = await ImageVoteService.vote(
            image_id=image_id,
            voter_id=voter_id,
            value=value,
            image_repo=image_repo,
            vote_repo=vote_repo,
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
