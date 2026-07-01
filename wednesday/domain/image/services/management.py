from __future__ import annotations

from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

from ..exceptions import ImageNotFoundError
from ..image import Image
from ..protocols import ImageRepo, VoteRepo
from ..vo import HiddenReason, HiddenState, ImageId


class ImageManagementService:
    """Catalog image hide/show orchestration."""

    @staticmethod
    async def hide(
        *,
        image_id: ImageId,
        actor: UserRole,
        image_repo: ImageRepo,
        at: AwareDatetime,
    ) -> Image:
        image_id = ImageId.ensure(image_id)
        actor = UserRole.ensure(actor)
        at = AwareDatetime.ensure(at)

        image = await image_repo.get_by_id(image_id)
        if image is None:
            raise ImageNotFoundError(str(image_id))

        image.hide(actor=actor, reason=HiddenReason.ADMIN, at=at)
        await image_repo.save(image)
        return image

    @staticmethod
    async def show(
        *,
        image_id: ImageId,
        actor: UserRole,
        image_repo: ImageRepo,
        vote_repo: VoteRepo,
        at: AwareDatetime,
    ) -> Image:
        image_id = ImageId.ensure(image_id)
        actor = UserRole.ensure(actor)
        at = AwareDatetime.ensure(at)

        image = await image_repo.get_by_id(image_id)
        if image is None:
            raise ImageNotFoundError(str(image_id))

        was_admin_hidden = isinstance(image.state, HiddenState) and image.state.reason == HiddenReason.ADMIN

        image.show(actor=actor, at=at)
        if was_admin_hidden:
            await vote_repo.reset(image_id)

        await image_repo.save(image)
        return image
