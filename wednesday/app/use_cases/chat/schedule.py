from zoneinfo import ZoneInfo

from domain.chat import (
    Chat,
    ChatId,
    ChatSchedule,
    ChatScheduleService,
    ManagementActor,
    Weekday,
)
from domain.kernel.vo import AwareDatetime

from .base import ChatBaseUseCase


class ChatScheduleUseCase(ChatBaseUseCase):
    """Domain chat schedule commands in a single UoW scope."""

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
            runner=lambda: ChatScheduleService.change_schedule_day(
                id=chat_id,
                actor=actor,
                new_weekday=new_weekday,
                repo=self._uow.chats,
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
            runner=lambda: ChatScheduleService.change_schedule_timezone(
                id=chat_id,
                actor=actor,
                timezone=timezone,
                repo=self._uow.chats,
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
            runner=lambda: ChatScheduleService.add_schedule(
                id=chat_id,
                actor=actor,
                schedule=schedule,
                repo=self._uow.chats,
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
            runner=lambda: ChatScheduleService.remove_schedule(
                id=chat_id,
                actor=actor,
                schedule=schedule,
                repo=self._uow.chats,
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
            runner=lambda: ChatScheduleService.clear_schedules(
                id=chat_id,
                actor=actor,
                repo=self._uow.chats,
                at=at,
            ),
        )
