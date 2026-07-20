from zoneinfo import ZoneInfo

from domain.kernel.vo import AwareDatetime

from ..chat import Chat
from ..exceptions import ValidationError
from ..protocols import ChatRepo
from ..vo import ChatId, ChatSchedule, ManagementActor, Weekday
from .utils import load_or_raise


class ChatScheduleService:
    """Load chat aggregate, apply schedule commands, and save."""

    @staticmethod
    async def change_schedule_day(
        *,
        id: ChatId,
        actor: ManagementActor,
        new_weekday: Weekday,
        repo: ChatRepo,
        at: AwareDatetime,
    ) -> Chat:
        id = ChatId.ensure(id)
        actor = ManagementActor.ensure(actor)
        new_weekday = Weekday.ensure(new_weekday)
        at = AwareDatetime.ensure(at)

        chat = await load_or_raise(repo=repo, id=id)
        chat.change_schedule_day(actor=actor, new_weekday=new_weekday, at=at)
        await repo.save(chat)
        return chat

    @staticmethod
    async def change_schedule_timezone(
        *,
        id: ChatId,
        actor: ManagementActor,
        timezone: ZoneInfo,
        repo: ChatRepo,
        at: AwareDatetime,
    ) -> Chat:
        id = ChatId.ensure(id)
        actor = ManagementActor.ensure(actor)
        at = AwareDatetime.ensure(at)
        if not isinstance(timezone, ZoneInfo):
            raise ValidationError("timezone must be a ZoneInfo")

        chat = await load_or_raise(repo=repo, id=id)
        chat.change_schedule_timezone(actor=actor, timezone=timezone, at=at)
        await repo.save(chat)
        return chat

    @staticmethod
    async def add_schedule(
        *,
        id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        repo: ChatRepo,
        at: AwareDatetime,
    ) -> Chat:
        id = ChatId.ensure(id)
        actor = ManagementActor.ensure(actor)
        schedule = ChatSchedule.ensure(schedule)
        at = AwareDatetime.ensure(at)

        chat = await load_or_raise(repo=repo, id=id)
        chat.add_schedule(actor=actor, schedule=schedule, at=at)
        await repo.save(chat)
        return chat

    @staticmethod
    async def remove_schedule(
        *,
        id: ChatId,
        actor: ManagementActor,
        schedule: ChatSchedule,
        repo: ChatRepo,
        at: AwareDatetime,
    ) -> Chat:
        id = ChatId.ensure(id)
        actor = ManagementActor.ensure(actor)
        schedule = ChatSchedule.ensure(schedule)
        at = AwareDatetime.ensure(at)

        chat = await load_or_raise(repo=repo, id=id)
        chat.remove_schedule(actor=actor, schedule=schedule, at=at)
        await repo.save(chat)
        return chat

    @staticmethod
    async def clear_schedules(
        *,
        id: ChatId,
        actor: ManagementActor,
        repo: ChatRepo,
        at: AwareDatetime,
    ) -> Chat:
        id = ChatId.ensure(id)
        actor = ManagementActor.ensure(actor)
        at = AwareDatetime.ensure(at)

        chat = await load_or_raise(repo=repo, id=id)
        chat.clear_schedules(actor=actor, at=at)
        await repo.save(chat)
        return chat
