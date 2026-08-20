from datetime import datetime
from uuid import UUID

from app.dto import ImageCard
from domain.chat import ChatId
from domain.image import ImageId, ImageNotFoundError, ImageRatingPolicy
from domain.kernel.vo import AwareDatetime

from .base import ImageBaseUseCase


class ImageCatalogUseCase(ImageBaseUseCase):
    """Catalog delivery use case methods."""

    async def pick_for_chat(self, *, chat_id: str) -> ImageCard | None:
        """Return an unseen catalog card. Does not record a view."""
        self._logger.debug("Image catalog pick started", chat_id=chat_id)
        async with self._uow:
            image_id = await self._uow.views.get_unseen_for_chat(
                chat_id=ChatId(UUID(chat_id)),
                min_rating=ImageRatingPolicy.SHOWABLE_RATING,
            )
            if image_id is None:
                self._logger.debug(
                    "No unseen images for chat",
                    chat_id=chat_id,
                )
                return None

            image = await self._uow.images.get_by_id(image_id)
            if image is None:
                raise ImageNotFoundError(str(image_id))

        self._logger.debug(
            "Catalog image picked for chat",
            chat_id=chat_id,
            image_id=str(image.id),
        )
        return ImageCard.from_domain(image)

    async def mark_shown(
        self,
        *,
        chat_id: str,
        image_id: str,
        at: datetime,
    ) -> None:
        """Record that the chat received this image (after a successful send)."""
        self._logger.debug(
            "Image catalog mark shown started",
            chat_id=chat_id,
            image_id=image_id,
        )
        async with self._uow:
            await self._uow.views.mark_shown(
                chat_id=ChatId(UUID(chat_id)),
                image_id=ImageId(UUID(image_id)),
                at=AwareDatetime.from_datetime(at),
            )
        self._logger.debug(
            "Image catalog mark shown finished",
            chat_id=chat_id,
            image_id=image_id,
        )

    async def reset_views(self, *, chat_id: str) -> int:
        self._logger.debug(
            "Image catalog reset views started",
            chat_id=chat_id,
        )
        async with self._uow:
            count = await self._uow.views.reset_for_chat(ChatId(UUID(chat_id)))
        self._logger.debug(
            "Image catalog reset views finished",
            chat_id=chat_id,
            count=count,
        )
        return count
