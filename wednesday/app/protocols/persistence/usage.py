from typing import Protocol

from domain.user import UsageStats, UserId


class IUsageRepo(Protocol):
    async def get_usage_stats(
        self,
        user_id: UserId,
    ) -> UsageStats: ...
