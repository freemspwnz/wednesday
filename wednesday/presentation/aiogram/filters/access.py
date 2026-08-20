"""Access filters for admin router (role-based)."""

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.dto import UserContext
from app.protocols import Logger


class AdminAccessFilter(BaseFilter):
    """Passes when the user has ADMIN or OWNER role in UserContext."""

    def __init__(self, logger: Logger) -> None:
        self._logger = logger.bind(module=self.__class__.__name__)

    async def __call__(
        self,
        event: TelegramObject,
        user: UserContext | None = None,
    ) -> bool:
        """Check if user has ADMIN or OWNER role."""
        if user is not None and user.is_admin:
            self._logger.debug("Admin access granted", user_id=user.tg_id)
            return True
        user_id = user.tg_id if user is not None else None
        self._logger.info("Admin access denied", user_id=user_id)
        return False
