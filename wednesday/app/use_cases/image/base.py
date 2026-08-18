from app.protocols import Logger, UoW
from domain.image import Image, ImageId, ImageNotFoundError, Vote
from domain.user import UserId


class ImageBaseUseCase:
    """Shared UoW + logging for image catalog command use cases."""

    _uow: UoW
    _logger: Logger

    def __init__(
        self,
        *,
        uow: UoW,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._logger = logger.bind(module=self.__class__.__name__)

    async def _load_image_or_raise(self, *, image_id: ImageId) -> Image:
        image = await self._uow.images.get_by_id(image_id)
        if image is None:
            raise ImageNotFoundError(str(image_id))
        return image

    async def _get_vote_if_exists(self, *, image_id: ImageId, voter_id: UserId) -> Vote | None:
        return await self._uow.votes.get(image_id, voter_id)
