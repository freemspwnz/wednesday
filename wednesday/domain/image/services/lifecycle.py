from domain.kernel import AwareDatetime
from domain.user import UserRole

from ..exceptions import ImageNotFoundError, ValidationError
from ..image import Image
from ..policies import Hide, ImageRatingPolicy, NoOperation, Show
from ..protocols import ImageRepo
from ..vo import HiddenReason, ImageId


class ImageLifecycleService:
    """Orchestrates image life cycle.
    - Change rating
    - Apply rating visibility
    """

    @staticmethod
    async def apply_vote(
        *,
        image_id: ImageId,
        new: int,
        old: int | None,
        repo: ImageRepo,
        at: AwareDatetime,
    ) -> Image:
        image_id = ImageId.ensure(image_id)
        at = AwareDatetime.ensure(at)

        image = await repo.get_by_id(image_id)
        if image is None:
            raise ImageNotFoundError(str(image_id))
        image.add_vote(new=new, old=old, at=at)
        ImageLifecycleService._apply_rating_visibility(image=image, at=at)
        await repo.save(image)
        return image

    @staticmethod
    def _apply_rating_visibility(*, image: Image, at: AwareDatetime) -> None:
        match ImageRatingPolicy.evaluate(image.rating, image.state):
            case NoOperation():
                return
            case Hide():
                image.hide(actor=UserRole.SYSTEM, reason=HiddenReason.RATING, at=at)
            case Show():
                image.show(actor=UserRole.SYSTEM, at=at)
            case _:
                raise ValidationError("unknown decision")
