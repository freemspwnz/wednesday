from __future__ import annotations

from uuid import NAMESPACE_DNS, UUID, uuid5
from zoneinfo import ZoneInfo

from app.dto import ChatContext, UserContext
from app.protocols import Logger
from domain.chat import Chat, ChatId, ChatProfile, ChatRepo, ChatScheduleSet, Weekday
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserProfile, UserRepo, UserRole, UserSubscription

UTC_TZ = ZoneInfo("UTC")


class RegistrationService:
    def __init__(self, *, logger: Logger) -> None:
        self._logger = logger.bind(module=self.__class__.__name__)

    async def get_or_create_user(
        self,
        dto: UserContext,
        repo: UserRepo,
    ) -> User:
        user_id = dto.id if dto.id is not None else self._user_id_from_tg(dto.tg_id)

        entity = await repo.get_by_id(user_id)
        if entity is not None:
            entity.mark_seen_at(at=AwareDatetime.now_utc())
            await repo.save(entity)
            self._logger.debug(
                "Existing user refreshed (last_seen)",
                user_id=str(entity.id),
                tg_id=dto.tg_id,
            )
            return entity

        now = AwareDatetime.now_utc()
        profile = UserProfile(
            telegram_id=dto.tg_id,
            is_bot=dto.is_bot,
            first_name=dto.first_name,
            last_name=dto.last_name,
            username=dto.username,
            language_code=dto.language_code,
            has_tg_premium=dto.has_tg_premium,
        )
        entity = User.register(
            id=user_id,
            profile=profile,
            role=dto.role or UserRole.USER,
            subscription=UserSubscription.free(now),
            now=now,
        )

        await repo.save(entity)
        self._logger.info(
            f"Entity created: {entity.id}",
            entity_type="user",
            entity_id=str(entity.id),
        )
        return entity

    async def get_or_create_chat(
        self,
        dto: ChatContext,
        repo: ChatRepo,
    ) -> Chat:
        chat_id = dto.id if dto.id is not None else self._chat_id_from_tg(dto.tg_id)

        entity = await repo.get_by_id(chat_id)
        if entity is not None:
            self._logger.debug(
                "Existing chat returned unchanged",
                chat_id=str(entity.id.value),
                tg_id=dto.tg_id,
            )
            return entity

        now = AwareDatetime.now_utc()
        profile = ChatProfile(
            type=dto.type,
            telegram_id=dto.tg_id,
            title=dto.title,
            username=dto.username,
        )
        schedules = ChatScheduleSet(
            timezone=dto.timezone or UTC_TZ,
            weekday=dto.weekday or Weekday.WEDNESDAY,
            schedules=dto.schedules,
        )
        entity = Chat.register(
            id=chat_id,
            profile=profile,
            schedules=schedules,
            at=now,
        )

        await repo.save(entity)
        self._logger.info(
            f"Entity created: {entity.id}",
            entity_type="chat",
            entity_id=str(entity.id),
        )
        return entity

    @staticmethod
    def _user_id_from_tg(tg_id: int) -> UserId:
        return UserId(UUID(str(uuid5(NAMESPACE_DNS, f"user:{tg_id}"))))

    @staticmethod
    def _chat_id_from_tg(tg_id: int) -> ChatId:
        return ChatId(UUID(str(uuid5(NAMESPACE_DNS, f"chat:{tg_id}"))))
