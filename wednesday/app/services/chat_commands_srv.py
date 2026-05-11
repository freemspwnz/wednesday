from __future__ import annotations

from zoneinfo import ZoneInfo

from app.exceptions import ChatNotFoundError
from app.protocols import Logger
from domain.chat import Chat, ChatId, ChatProfile, ChatRepo, ChatSchedule, ManagementActor, Weekday
from domain.kernel.vo import AwareDatetime


class ChatCommandService:
    """Загрузка агрегата Chat, доменная команда и save (транзакцию закрывает UoW)."""

    def __init__(self, *, logger: Logger) -> None:
        self._logger = logger.bind(module=self.__class__.__name__)

    @staticmethod
    async def _load_chat_or_raise(repo: ChatRepo, chat_id: ChatId) -> Chat:
        entity = await repo.get_by_id(chat_id)
        if entity is None:
            raise ChatNotFoundError(chat_id)
        return entity

    async def change_profile(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        new_profile: ChatProfile,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.change_profile(actor=actor, new_profile=new_profile, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="change_profile",
            chat_id=str(chat.id.value),
        )
        return chat

    async def change_schedule_day(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        new_weekday: Weekday,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.change_schedule_day(actor=actor, new_weekday=new_weekday, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="change_schedule_day",
            chat_id=str(chat.id.value),
            new_weekday=str(new_weekday),
        )
        return chat

    async def change_schedule_timezone(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        timezone: ZoneInfo,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.change_schedule_timezone(actor=actor, timezone=timezone, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="change_schedule_timezone",
            chat_id=str(chat.id.value),
            timezone=str(timezone),
        )
        return chat

    async def add_schedule(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.add_schedule(actor=actor, schedule=schedule, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="add_schedule",
            chat_id=str(chat.id.value),
            schedule_hour=schedule.hour,
            schedule_minute=schedule.minute,
        )
        return chat

    async def remove_schedule(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.remove_schedule(actor=actor, schedule=schedule, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="remove_schedule",
            chat_id=str(chat.id.value),
        )
        return chat

    async def clear_schedules(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.clear_schedules(actor=actor, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="clear_schedules",
            chat_id=str(chat.id.value),
        )
        return chat

    async def activate(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.activate(actor=actor, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="activate",
            chat_id=str(chat.id.value),
        )
        return chat

    async def deactivate(
        self,
        *,
        repo: ChatRepo,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(repo, chat_id)
        chat.deactivate(actor=actor, at=at)
        await repo.save(chat)
        self._logger.info(
            "Chat aggregate updated",
            action="deactivate",
            chat_id=str(chat.id.value),
        )
        return chat
