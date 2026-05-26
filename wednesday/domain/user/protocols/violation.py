from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError
from ..policies import ViolationStats
from ..vo import UserId


@runtime_checkable
class ViolationRepo(Protocol):
    """Violation repository protocol."""

    async def get_violation_stats(
        self,
        user_id: UserId,
    ) -> ViolationStats:
        """Get violation stats by user ID."""
        ...

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, cls):
            raise ValidationError("repo must be a ViolationRepo")
        return repo
