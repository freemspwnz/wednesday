from dataclasses import dataclass
from datetime import date
from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError
from ..policies import UsageStats
from ..vo import AwareDatetime, UserId


@dataclass(frozen=True)
class UsageSnapshot:
    last_usage: AwareDatetime | None
    daily_usage: int
    daily_usage_on: date


@runtime_checkable
class UsageRepo(Protocol):
    """Usage repository protocol."""

    async def get_stats(
        self,
        user_id: UserId,
        at: AwareDatetime,
        lock: bool = False,
    ) -> UsageStats:
        """Get usage stats by user ID."""
        ...

    async def record(
        self,
        user_id: UserId,
        at: AwareDatetime,
    ) -> UsageSnapshot:
        """Record usage by user ID."""
        ...

    async def refund(
        self,
        user_id: UserId,
        snapshot: UsageSnapshot,
    ) -> None:
        """Refund usage by user ID."""
        ...

    @classmethod
    def ensure(cls, repo: object) -> Self:
        if not isinstance(repo, cls):
            raise ValidationError(f"Repository must be an instance of {cls.__name__}")
        return repo
