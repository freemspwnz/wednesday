from domain.image import Image, ImageId, ImageManagementService, ImageVoteService
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
            image = await ImageManagementService.hide(
                id=image_id,
                actor=actor,
                repo=self._uow.images,
                at=at,
            )
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
            image = await ImageManagementService.show(
                id=image_id,
                actor=actor,
                repo=self._uow.images,
                at=at,
            )
            if actor == UserRole.OWNER:
                await ImageVoteService.reset(id=image_id, repo=self._uow.votes)
        self._logger.info(
            "Image aggregate updated",
            action="show",
            image_id=str(image.id.value),
        )
        return image
