from domain.chat import ChatId
from domain.kernel import AwareDatetime

from ..policies import ImageRatingPolicy
from ..protocols import ViewRepo
from ..vo import ImageId


class ImageCatalogService:
    """Catalog delivery: pick unseen selectable image and record the view."""

    @staticmethod
    async def pick_for_chat(
        *,
        chat_id: ChatId,
        repo: ViewRepo,
        at: AwareDatetime,
    ) -> ImageId | None:
        chat_id = ChatId.ensure(chat_id)
        at = AwareDatetime.ensure(at)

        image_id = await repo.get_unseen_for_chat(
            chat_id=chat_id,
            min_rating=ImageRatingPolicy.SHOWABLE_RATING,
        )
        if image_id is None:
            return None

        await repo.mark_shown(chat_id, image_id, at=at)
        return image_id
