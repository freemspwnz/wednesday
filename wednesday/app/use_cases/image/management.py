from domain.image import HiddenReason, Image, ImageId
from domain.kernel import AwareDatetime
from domain.user import UserRole

from .base import ImageBaseUseCase


class ImageManagementUseCase(ImageBaseUseCase):
    """Catalog image hide/show use case methods."""

    async def hide(
        self,
        *,
        image_id: ImageId,
        actor: UserRole,
        at: AwareDatetime,
    ) -> Image:
        self._logger.debug(
            "Image hide scenario started",
            image_id=str(image_id.value),
            actor=str(actor),
        )
        async with self._uow:
            image = await self._load_image_or_raise(image_id=image_id)
            image.hide(actor=actor, reason=HiddenReason.ADMIN, at=at)
            await self._uow.images.save(image)
        self._logger.info(
            "Image aggregate updated",
            action="hide",
            image_id=str(image.id.value),
        )
        return image

    async def show(
        self,
        *,
        image_id: ImageId,
        actor: UserRole,
        at: AwareDatetime,
    ) -> Image:
        self._logger.debug(
            "Image show scenario started",
            image_id=str(image_id.value),
            actor=str(actor),
        )
        async with self._uow:
            image = await self._load_image_or_raise(image_id=image_id)
            image.show(actor=actor, at=at)
            await self._uow.images.save(image)
            if actor == UserRole.OWNER:
                await self._uow.votes.reset(image_id)
        self._logger.info(
            "Image aggregate updated",
            action="show",
            image_id=str(image.id.value),
        )
        return image
