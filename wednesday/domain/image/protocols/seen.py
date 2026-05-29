from typing import Protocol
from uuid import UUID

from ..vo import AwareDatetime, ImageId


class ImageSeenRepo(Protocol):
    """Per-chat image seen facts; key (chat_id, image_id) without user_id."""

    async def is_seen(self, chat_id: UUID, image_id: ImageId) -> bool:
        """Whether chat has been shown this image."""
        ...

    async def mark_seen(
        self,
        chat_id: UUID,
        image_id: ImageId,
        at: AwareDatetime,
    ) -> None:
        """Record seen; idempotent."""
        ...
