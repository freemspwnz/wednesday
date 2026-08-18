from app.dto import ImageCard
from domain.chat import ChatId
from domain.image import ImageNotFoundError, ImageRatingPolicy
from domain.kernel.vo import AwareDatetime

from .base import ImageBaseUseCase


class ImageCatalogUseCase(ImageBaseUseCase):
    """Catalog delivery use case methods."""

    async def pick_for_chat(
        self,
        *,
        chat_id: ChatId,
        at: AwareDatetime,
    ) -> ImageCard | None:
        self._logger.debug("Image catalog pick started", chat_id=str(chat_id.value))
        async with self._uow:
            image_id = await self._uow.views.get_unseen_for_chat(
                chat_id=chat_id,
                min_rating=ImageRatingPolicy.SHOWABLE_RATING,
            )
            if image_id is None:
                self._logger.debug(
                    "No unseen images for chat",
                    chat_id=str(chat_id.value),
                )
                return None

            image = await self._uow.images.get_by_id(image_id)
            if image is None:
                raise ImageNotFoundError(str(image_id))
            await self._uow.views.mark_shown(chat_id, image_id, at=at)

        self._logger.debug(
            "Catalog image picked for chat",
            chat_id=str(chat_id.value),
            image_id=str(image.id.value),
        )
        return ImageCard.from_domain(image)
