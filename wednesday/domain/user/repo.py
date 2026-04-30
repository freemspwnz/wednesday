from typing import Protocol

from .aggregate import User
from .vo import UserTelegramId


class UserRepo(Protocol):
    """User repository protocol."""

    async def get_by_id(self, user_id: UserTelegramId) -> User | None:
        """Get user by ID."""
        ...

    async def save(self, user: User) -> None:
        """Save user."""
        ...

    async def exists(self, user_id: UserTelegramId) -> bool:
        """Check if user exists."""
        ...
