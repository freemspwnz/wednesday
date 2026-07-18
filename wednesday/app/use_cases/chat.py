from collections.abc import Awaitable, Callable
from zoneinfo import ZoneInfo

from app.dto import ChatContext
from app.protocols import CacheRepo, Logger, UoW
from domain.chat import Chat, ChatId, ChatProfile, ChatSchedule, ManagementActor, Weekday
from domain.kernel.vo import AwareDatetime

from ..services import ChatCommandService


class ChatCommandsUseCase:
    """Domain chat commands in a single UoW scope."""

    def __init__(
        self,
        *,
        uow: UoW,
        service: ChatCommandService,
        cache: CacheRepo[ChatContext, Chat],
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._service = service
        self._cache = cache
        self._logger = logger.bind(module=self.__class__.__name__)

    def _log_scenario_start(self, *, action: str, chat_id: ChatId) -> None:
        self._logger.debug(
            "Chat command scenario started",
            action=action,
            chat_id=str(chat_id.value),
        )

    async def _run_mutating(
        self,
        *,
        action: str,
        chat_id: ChatId,
        runner: Callable[[], Awaitable[Chat]],
    ) -> Chat:
        self._log_scenario_start(action=action, chat_id=chat_id)
        async with self._uow:
            chat = await runner()
        await self._cache.set(chat)
        self._logger.debug(
            "Chat cache snapshot refreshed",
            action=action,
            tg_id=chat.profile.telegram_id,
        )
        return chat

    async def change_profile(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        new_profile: ChatProfile,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="change_profile",
            chat_id=chat_id,
            runner=lambda: self._service.change_profile(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                new_profile=new_profile,
                at=at,
            ),
        )

    async def change_schedule_day(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        new_weekday: Weekday,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="change_schedule_day",
            chat_id=chat_id,
            runner=lambda: self._service.change_schedule_day(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                new_weekday=new_weekday,
                at=at,
            ),
        )

    async def change_schedule_timezone(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        timezone: ZoneInfo,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="change_schedule_timezone",
            chat_id=chat_id,
            runner=lambda: self._service.change_schedule_timezone(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                timezone=timezone,
                at=at,
            ),
        )

    async def add_schedule(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="add_schedule",
            chat_id=chat_id,
            runner=lambda: self._service.add_schedule(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                schedule=schedule,
                at=at,
            ),
        )

    async def remove_schedule(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="remove_schedule",
            chat_id=chat_id,
            runner=lambda: self._service.remove_schedule(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                schedule=schedule,
                at=at,
            ),
        )

    async def clear_schedules(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="clear_schedules",
            chat_id=chat_id,
            runner=lambda: self._service.clear_schedules(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                at=at,
            ),
        )

    async def activate(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="activate",
            chat_id=chat_id,
            runner=lambda: self._service.activate(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                at=at,
            ),
        )

    async def deactivate(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="deactivate",
            chat_id=chat_id,
            runner=lambda: self._service.deactivate(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                at=at,
            ),
        )
