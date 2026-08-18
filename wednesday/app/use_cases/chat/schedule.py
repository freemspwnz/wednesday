from zoneinfo import ZoneInfo

from domain.chat import (
    Chat,
    ChatId,
    ChatSchedule,
    ManagementActor,
    ValidationError,
    Weekday,
)
from domain.kernel.vo import AwareDatetime

from .base import ChatBaseUseCase


class ChatScheduleUseCase(ChatBaseUseCase):
    """Domain chat schedule commands in a single UoW scope."""

    async def list_due(self, *, at: AwareDatetime) -> list[Chat]:
        """Return active chats whose schedule matches ``at`` (timezone + weekday)."""
        at = AwareDatetime.ensure(at)
        self._logger.debug("Chat schedule due scan started", at=str(at))
        async with self._uow:
            candidates = await self._uow.chats.list_active_scheduled()
        due = [chat for chat in candidates if chat.is_due_at(at)]
        self._logger.info(
            "Chat schedule due scan finished",
            candidates=len(candidates),
            due=len(due),
        )
        return due

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
            runner=lambda: self._change_schedule_day(
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
            runner=lambda: self._change_schedule_timezone(
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
            runner=lambda: self._add_schedule(
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
            runner=lambda: self._remove_schedule(
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
            runner=lambda: self._clear_schedules(chat_id=chat_id, actor=actor, at=at),
        )

    async def _change_schedule_day(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        new_weekday: Weekday,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.change_schedule_day(actor=actor, new_weekday=new_weekday, at=at)
        await self._uow.chats.save(chat)
        return chat

    async def _change_schedule_timezone(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        timezone: ZoneInfo,
        at: AwareDatetime,
    ) -> Chat:
        if not isinstance(timezone, ZoneInfo):
            raise ValidationError("timezone must be a ZoneInfo")
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.change_schedule_timezone(actor=actor, timezone=timezone, at=at)
        await self._uow.chats.save(chat)
        return chat

    async def _add_schedule(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.add_schedule(actor=actor, schedule=schedule, at=at)
        await self._uow.chats.save(chat)
        return chat

    async def _remove_schedule(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.remove_schedule(actor=actor, schedule=schedule, at=at)
        await self._uow.chats.save(chat)
        return chat

    async def _clear_schedules(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.clear_schedules(actor=actor, at=at)
        await self._uow.chats.save(chat)
        return chat
