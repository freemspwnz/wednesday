from __future__ import annotations

from uuid import UUID

from app.dto import ImageCard
from app.protocols import Logger
from domain.image import ImageRepo, ImageSeenRepo
from domain.kernel.vo import AwareDatetime

_MIN_SCORE = 1


class ImageRandomService:
    """Подбор случайного непросмотренного изображения для чата и отметка seen."""

    def __init__(self, *, logger: Logger) -> None:
        self._logger = logger.bind(module=self.__class__.__name__)

    async def pick_for_chat(
        self,
        *,
        images: ImageRepo,
        seen: ImageSeenRepo,
        chat_id: UUID,
        at: AwareDatetime,
    ) -> ImageCard | None:
        image = await images.get_random_unseen_for_chat(chat_id, min_score=_MIN_SCORE)
        if image is None:
            self._logger.debug("No unseen images for chat", chat_id=str(chat_id))
            return None

        await seen.mark_seen(chat_id, image.id, at=at)
        self._logger.debug(
            "Random image picked for chat",
            chat_id=str(chat_id),
            image_id=str(image.id.value),
        )
        return ImageCard.from_domain(image)
