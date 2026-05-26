from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError
from ..policies import UsageStats
from ..user import UserId


@runtime_checkable
class UsageRepo(Protocol):
    """Usage repository protocol."""

    async def get_usage_stats(
        self,
        user_id: UserId,
    ) -> UsageStats:
        """Get usage stats by user ID."""
        ...

    @classmethod
    def ensure(cls, repo: Self) -> Self:
        if not isinstance(repo, cls):
            raise ValidationError("repo must be a UsageRepo")
        return repo
