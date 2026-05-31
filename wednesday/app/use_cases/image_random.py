from __future__ import annotations

from uuid import UUID

from app.dto import ImageCard
from app.protocols import Logger, UoW
from domain.kernel.vo import AwareDatetime

from ..services import ImageRandomService


class ImageRandomUseCase:
    """Случайное непросмотренное изображение для чата в одной транзакции UoW."""

    def __init__(
        self,
        *,
        uow: UoW,
        image_random: ImageRandomService,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._image_random = image_random
        self._logger = logger.bind(module=self.__class__.__name__)

    async def pick_for_chat(
        self,
        *,
        chat_id: UUID,
        at: AwareDatetime,
    ) -> ImageCard | None:
        self._logger.debug("Image random scenario started", chat_id=str(chat_id))
        async with self._uow:
            return await self._image_random.pick_for_chat(
                images=self._uow.images,
                seen=self._uow.seen,
                chat_id=chat_id,
                at=at,
            )
