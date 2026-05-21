"""Admin router middleware: access check and denial message."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.dto import UserContext
from app.protocols import Logger
from domain.user import UserRole

from ...messages import access as access_msg


class AdminAccessMiddleware(BaseMiddleware):
    """Checks admin access for all handlers on the admin router.

    On denial, sends an error message and does not invoke the handler.
    """

    def __init__(
        self,
        *,
        admin_id: int,
        logger: Logger,
    ) -> None:
        self._admin_id = admin_id
        self._logger = logger.bind(module=self.__class__.__name__)

    @staticmethod
    def is_admin(user: UserContext, admin_id: int) -> bool:
        if user.tg_id == admin_id:
            return True
        return user.role in {UserRole.ADMIN, UserRole.OWNER}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401  # aiogram middleware return type
        user = data.get("user")
        if not isinstance(user, UserContext):
            self._logger.warning("User is missing in middleware data")
            return None

        if self.is_admin(user, self._admin_id):
            self._logger.debug("Admin access granted", user_id=user.tg_id)
            return await handler(event, data)

        self._logger.info("Admin access denied", user_id=user.tg_id)

        if isinstance(event, Message):
            await event.answer(access_msg.ADMIN_DENIED)

        return None
