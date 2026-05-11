from __future__ import annotations

from zoneinfo import ZoneInfo

from app.protocols import IUoW, Logger
from domain.chat import Chat, ChatId, ChatProfile, ChatSchedule, ManagementActor, Weekday
from domain.kernel.vo import AwareDatetime

from ..services import ChatCommandService


class ChatCommandsUseCase:
    """Фасад доменных команд chat-агрегата в рамках одной транзакции UoW."""

    def __init__(
        self,
        *,
        uow: IUoW,
        chat_commands: ChatCommandService,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._chat_commands = chat_commands
        self._logger = logger.bind(module=self.__class__.__name__)

    def _log_scenario_start(self, *, action: str, chat_id: ChatId) -> None:
        self._logger.debug(
            "Chat command scenario started",
            action=action,
            chat_id=str(chat_id.value),
        )

    async def change_profile(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        new_profile: ChatProfile,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="change_profile", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.change_profile(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                new_profile=new_profile,
                at=at,
            )

    async def change_schedule_day(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        new_weekday: Weekday,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="change_schedule_day", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.change_schedule_day(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                new_weekday=new_weekday,
                at=at,
            )

    async def change_schedule_timezone(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        timezone: ZoneInfo,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="change_schedule_timezone", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.change_schedule_timezone(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                timezone=timezone,
                at=at,
            )

    async def add_schedule(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="add_schedule", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.add_schedule(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                schedule=schedule,
                at=at,
            )

    async def remove_schedule(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="remove_schedule", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.remove_schedule(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                schedule=schedule,
                at=at,
            )

    async def clear_schedules(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="clear_schedules", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.clear_schedules(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                at=at,
            )

    async def activate(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="activate", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.activate(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                at=at,
            )

    async def deactivate(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        self._log_scenario_start(action="deactivate", chat_id=chat_id)
        async with self._uow:
            return await self._chat_commands.deactivate(
                repo=self._uow.chats,
                chat_id=chat_id,
                actor=actor,
                at=at,
            )
