from typing import Protocol

from domain.user import UserId, ViolationStats


class IViolationRepo(Protocol):
    """Подсчёт нарушений пользователя."""

    async def get_violation_stats(
        self,
        user_id: UserId,
    ) -> ViolationStats: ...
