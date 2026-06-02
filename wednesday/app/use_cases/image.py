from uuid import UUID

from app.dto import ImageCard
from app.protocols import Logger, UoW
from domain.image import Image, ImageId
from domain.kernel.vo import AwareDatetime

from ..services import ImageCommandService


class ImageCommandsUseCase:
    """Image catalog commands in a single UoW scope."""

    def __init__(
        self,
        *,
        uow: UoW,
        image_commands: ImageCommandService,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._image_commands = image_commands
        self._logger = logger.bind(module=self.__class__.__name__)

    async def pick_for_chat(
        self,
        *,
        chat_id: UUID,
        at: AwareDatetime,
    ) -> ImageCard | None:
        self._logger.debug("Image random scenario started", chat_id=str(chat_id))
        async with self._uow:
            return await self._image_commands.pick_for_chat(
                images=self._uow.images,
                seen=self._uow.seen,
                chat_id=chat_id,
                at=at,
            )

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
            return await self._image_commands.vote(
                image_id=image_id,
                voter_id=voter_id,
                value=value,
                image_repo=self._uow.images,
                vote_repo=self._uow.votes,
                at=at,
            )
