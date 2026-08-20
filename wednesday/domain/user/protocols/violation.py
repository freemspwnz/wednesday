from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError
from ..policies import ViolationStats
from ..vo import AwareDatetime, UserId


@runtime_checkable
class ViolationRepo(Protocol):
    """Violation repository protocol."""

    async def get_violation_stats(
        self,
        user_id: UserId,
    ) -> ViolationStats:
        """Get violation stats by user ID."""
        ...

    async def record_violation(
        self,
        user_id: UserId,
        at: AwareDatetime,
    ) -> None:
        """Record violation by user ID."""
        ...

    @classmethod
    def ensure(cls, repo: object) -> Self:
        if not isinstance(repo, cls):
            raise ValidationError(f"Repository must be an instance of {cls.__name__}")
        return repo
