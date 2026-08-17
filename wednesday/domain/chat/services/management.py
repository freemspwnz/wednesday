from typing import ClassVar
from zoneinfo import ZoneInfo

from domain.kernel.vo import AwareDatetime

from ..chat import Chat
from ..protocols import ChatRepo
from ..vo import ChatId, ChatProfile, ChatScheduleSet, ManagementActor, Weekday
from .utils import chat_id_from_tg, load_or_raise


class ChatManagementService:
    """Load chat aggregate, apply profile/lifecycle commands, and save."""

    _UTC: ClassVar[ZoneInfo] = ZoneInfo("UTC")

    @classmethod
    async def get_or_create(
        cls,
        *,
        profile: ChatProfile,
        repo: ChatRepo,
        at: AwareDatetime,
    ) -> Chat:
        profile = ChatProfile.ensure(profile)
        at = AwareDatetime.ensure(at)
        chat_id = chat_id_from_tg(profile.telegram_id)

        existing = await repo.get_by_id(chat_id)
        if existing is not None:
            return existing

        chat = Chat.register(
            id=chat_id,
            profile=profile,
            schedules=ChatScheduleSet(
                timezone=cls._UTC,
                weekday=Weekday.WEDNESDAY,
                schedules=(),
            ),
            at=at,
        )
        await repo.save(chat)
        return chat

    @staticmethod
    async def get_if_exists(*, tg_id: int, repo: ChatRepo) -> Chat | None:
        return await repo.get_by_id(chat_id_from_tg(tg_id))

    @staticmethod
    async def change_profile(
        *,
        id: ChatId,
        actor: ManagementActor,
        new_profile: ChatProfile,
        repo: ChatRepo,
        at: AwareDatetime,
    ) -> Chat:
        id = ChatId.ensure(id)
        actor = ManagementActor.ensure(actor)
        new_profile = ChatProfile.ensure(new_profile)
        at = AwareDatetime.ensure(at)

        chat = await load_or_raise(repo=repo, id=id)
        chat.change_profile(actor=actor, new_profile=new_profile, at=at)
        await repo.save(chat)
        return chat

    @staticmethod
    async def activate(
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
        chat.activate(actor=actor, at=at)
        await repo.save(chat)
        return chat

    @staticmethod
    async def deactivate(
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
        chat.deactivate(actor=actor, at=at)
        await repo.save(chat)
        return chat
