from __future__ import annotations

from uuid import UUID

from app.protocols import Logger, UoW
from domain.image import Image, ImageId, ImageVoteService
from domain.kernel.vo import AwareDatetime


class ImageVoteUseCase:
    """Голосование за изображение в одной транзакции UoW."""

    def __init__(
        self,
        *,
        uow: UoW,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._logger = logger.bind(module=self.__class__.__name__)

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
            return await ImageVoteService.vote(
                image_id=image_id,
                voter_id=voter_id,
                value=value,
                image_repo=self._uow.images,
                vote_repo=self._uow.votes,
                at=at,
            )
