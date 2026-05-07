from typing import Protocol

from .user import User
from .vo import UserId


class UserRepo(Protocol):
    """User repository protocol."""

    async def get_by_id(self, user_id: UserId) -> User | None:
        """Get user by ID."""
        ...

    async def save(self, user: User) -> None:
        """Save user."""
        ...

    async def exists(self, user_id: UserId) -> bool:
        """Check if user exists."""
        ...
