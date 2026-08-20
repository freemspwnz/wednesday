from datetime import datetime
from uuid import UUID

from domain.image import HiddenReason, Image, ImageId
from domain.kernel import AwareDatetime
from domain.user import UserRole

from .base import ImageBaseUseCase


class ImageManagementUseCase(ImageBaseUseCase):
    """Catalog image hide/show use case methods."""

    async def hide(
        self,
        *,
        image_id: str,
        actor: int,
        at: datetime,
    ) -> Image:
        self._logger.debug(
            "Image hide scenario started",
            image_id=image_id,
            actor=actor,
        )
        async with self._uow:
            image = await self._load_image_or_raise(image_id=ImageId(UUID(image_id)))
            image.hide(
                actor=UserRole(actor),
                reason=HiddenReason.ADMIN,
                at=AwareDatetime.from_datetime(at),
            )
            await self._uow.images.save(image)
        self._logger.info(
            "Image aggregate updated",
            action="hide",
            image_id=image_id,
        )
        return image

    async def show(
        self,
        *,
        image_id: str,
        actor: int,
        at: datetime,
    ) -> Image:
        self._logger.debug(
            "Image show scenario started",
            image_id=image_id,
            actor=actor,
        )
        async with self._uow:
            image = await self._load_image_or_raise(image_id=ImageId(UUID(image_id)))
            image.show(actor=UserRole(actor), at=AwareDatetime.from_datetime(at))
            await self._uow.images.save(image)
            if UserRole(actor) == UserRole.OWNER:
                await self._uow.votes.reset(ImageId(UUID(image_id)))
        self._logger.info(
            "Image aggregate updated",
            action="show",
            image_id=image_id,
        )
        return image
