from typing import Protocol
from uuid import UUID

from ..vo import AwareDatetime, ImageId


class ViewRepo(Protocol):
    """Per-chat image view facts; key (chat_id, image_id)."""

    async def was_shown(self, chat_id: UUID, image_id: ImageId) -> bool:
        """Whether chat already viewed this image."""
        ...

    async def mark_shown(
        self,
        chat_id: UUID,
        image_id: ImageId,
        at: AwareDatetime,
    ) -> None:
        """Record view; idempotent."""
        ...
