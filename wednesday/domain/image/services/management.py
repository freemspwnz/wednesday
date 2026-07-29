from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

from ..exceptions import ImageNotFoundError
from ..image import Image
from ..protocols import ImageRepo
from ..vo import HiddenReason, ImageId


class ImageManagementService:
    """Catalog image hide/show orchestration."""

    @staticmethod
    async def hide(
        *,
        id: ImageId,
        actor: UserRole,
        repo: ImageRepo,
        at: AwareDatetime,
    ) -> Image:
        id = ImageId.ensure(id)
        actor = UserRole.ensure(actor)
        at = AwareDatetime.ensure(at)

        image = await repo.get_by_id(id)
        if image is None:
            raise ImageNotFoundError(str(id))

        image.hide(actor=actor, reason=HiddenReason.ADMIN, at=at)
        await repo.save(image)
        return image

    @staticmethod
    async def show(
        *,
        id: ImageId,
        actor: UserRole,
        repo: ImageRepo,
        at: AwareDatetime,
    ) -> Image:
        id = ImageId.ensure(id)
        actor = UserRole.ensure(actor)
        at = AwareDatetime.ensure(at)

        image = await repo.get_by_id(id)
        if image is None:
            raise ImageNotFoundError(str(id))

        image.show(actor=actor, at=at)

        await repo.save(image)
        return image
