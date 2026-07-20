from uuid import UUID

from app.dto import ImageCard
from app.protocols import Logger, UoW
from domain.image import Image, ImageCatalogService, ImageId, ImageVoteService
from domain.kernel.vo import AwareDatetime


class ImageCommandsUseCase:
    """Image catalog commands in a single UoW scope."""

    def __init__(
        self,
        *,
        uow: UoW,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._logger = logger.bind(module=self.__class__.__name__)

    async def pick_for_chat(
        self,
        *,
        chat_id: UUID,
        at: AwareDatetime,
    ) -> ImageCard | None:
        self._logger.debug("Image random scenario started", chat_id=str(chat_id))
        async with self._uow:
            image = await ImageCatalogService.pick_for_chat(
                chat_id=chat_id,
                image_repo=self._uow.images,
                view_repo=self._uow.views,
                at=at,
            )
        if image is None:
            self._logger.debug("No unseen images for chat", chat_id=str(chat_id))
            return None
        self._logger.debug(
            "Random image picked for chat",
            chat_id=str(chat_id),
            image_id=str(image.id.value),
        )
        return ImageCard.from_domain(image)

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
