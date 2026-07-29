from typing import Protocol, runtime_checkable

from domain.user import UserId

from ..vo import ImageId
from ..vote import Vote


@runtime_checkable
class VoteRepo(Protocol):
    """One vote per (image_id, voter_id), values -1 or +1."""

    async def get(self, image_id: ImageId, voter_id: UserId) -> Vote | None:
        """Get vote if present."""
        ...

    async def upsert(self, vote: Vote) -> None:
        """Insert or update vote."""
        ...

    async def list_for_image(self, image_id: ImageId) -> list[Vote]:
        """All votes for rating recalculation."""
        ...

    async def reset(self, image_id: ImageId) -> None:
        """Reset all votes for an image."""
        ...
