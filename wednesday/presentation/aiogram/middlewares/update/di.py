from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.protocols import Logger, ScopeFactory


class DIMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        scope_factory: ScopeFactory,
        logger: Logger,
    ) -> None:
        self._scope_factory = scope_factory
        self._logger = logger.bind(module=self.__class__.__name__)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401  # aiogram handler return type
        async with self._scope_factory() as scope:
            self._logger.debug("Scope container created")
            data["scope"] = scope
            data["logger"] = scope.logger
            return await handler(event, data)
