from typing import Protocol, runtime_checkable

from domain.chat import ChatId

from ..vo import AwareDatetime, ImageId


@runtime_checkable
class ViewRepo(Protocol):
    """Per-chat image view facts; key (chat_id, image_id)."""

    async def was_shown(
        self,
        chat_id: ChatId,
        image_id: ImageId,
    ) -> bool:
        """Whether chat already viewed this image."""
        ...

    async def mark_shown(
        self,
        chat_id: ChatId,
        image_id: ImageId,
        at: AwareDatetime,
    ) -> None:
        """Record view; idempotent."""
        ...

    async def get_unseen_for_chat(
        self,
        chat_id: ChatId,
        min_rating: int,
    ) -> ImageId | None:
        """Get unseen image for chat."""
        ...
