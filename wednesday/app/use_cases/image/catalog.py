from uuid import UUID

from app.dto import ImageCard
from domain.image import ImageCatalogService
from domain.kernel.vo import AwareDatetime

from .base import ImageBaseUseCase


class ImageCatalogUseCase(ImageBaseUseCase):
    """Catalog delivery use case methods."""

    async def pick_for_chat(
        self,
        *,
        chat_id: UUID,
        at: AwareDatetime,
    ) -> ImageCard | None:
        self._logger.debug("Image catalog pick started", chat_id=str(chat_id))
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
            "Catalog image picked for chat",
            chat_id=str(chat_id),
            image_id=str(image.id.value),
        )
        return ImageCard.from_domain(image)
