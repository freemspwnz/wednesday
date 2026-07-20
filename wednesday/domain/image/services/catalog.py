from __future__ import annotations

from uuid import UUID

from domain.kernel.vo import AwareDatetime

from ..exceptions import ValidationError
from ..image import Image
from ..policies import ImageScorePolicy
from ..protocols import ImageRepo, ViewRepo


class ImageCatalogService:
    """Catalog delivery: pick unseen selectable image and record the view."""

    @staticmethod
    async def pick_for_chat(
        *,
        chat_id: UUID,
        image_repo: ImageRepo,
        view_repo: ViewRepo,
        at: AwareDatetime,
    ) -> Image | None:
        if not isinstance(chat_id, UUID):
            raise ValidationError("chat_id must be a UUID")
        at = AwareDatetime.ensure(at)

        image = await image_repo.get_random_unseen_for_chat(
            chat_id,
            min_score=ImageScorePolicy.CATALOG_MIN_SCORE,
        )
        if image is None:
            return None

        await view_repo.mark_shown(chat_id, image.id, at=at)
        return image
