from uuid import NAMESPACE_DNS, UUID, uuid5
from zoneinfo import ZoneInfo

from app.protocols import Logger
from domain.catalog import ModelCatalog, SubscriptionCatalog
from domain.chat import Chat, ChatId, ChatProfile, ChatRepo, ChatScheduleSet, Weekday
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserProfile, UserRepo, UserRole, UserSettings, UserSubscription

UTC_TZ = ZoneInfo("UTC")


class RegistrationService:
    def __init__(
        self,
        *,
        model_catalog: ModelCatalog,
        subscription_catalog: SubscriptionCatalog,
        logger: Logger,
    ) -> None:
        self._model_catalog = model_catalog
        self._subscription_catalog = subscription_catalog
        self._logger = logger.bind(module=self.__class__.__name__)

    async def get_or_create_user(
        self,
        profile: UserProfile,
        repo: UserRepo,
    ) -> User:
        user_id = self.user_id_from_tg(profile.telegram_id)

        entity = await repo.get_by_id(user_id)
        if entity is not None:
            entity.mark_seen_at(at=AwareDatetime.now_utc())
            await repo.save(entity)
            self._logger.debug(
                "Existing user refreshed (last_seen)",
                user_id=str(entity.id),
                tg_id=profile.telegram_id,
            )
            return entity

        now = AwareDatetime.now_utc()
        default_plan = await self._subscription_catalog.default_plan()
        default_descriptor = await self._model_catalog.default_for_tier(default_plan.tier)
        entity = User.register(
            id=user_id,
            profile=profile,
            role=UserRole.USER,
            subscription=UserSubscription(
                plan=default_plan,
                started_at=now,
                expires_at=None,
            ),
            settings=UserSettings.from_descriptor(default_descriptor),
            at=now,
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
        profile: ChatProfile,
        repo: ChatRepo,
    ) -> Chat:
        chat_id = self.chat_id_from_tg(profile.telegram_id)

        entity = await repo.get_by_id(chat_id)
        if entity is not None:
            self._logger.debug(
                "Existing chat returned unchanged",
                chat_id=str(entity.id.value),
                tg_id=profile.telegram_id,
            )
            return entity

        now = AwareDatetime.now_utc()
        schedules = ChatScheduleSet(
            timezone=UTC_TZ,
            weekday=Weekday.WEDNESDAY,
            schedules=(),
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

    async def get_user_if_exists(
        self,
        *,
        tg_id: int,
        repo: UserRepo,
    ) -> User | None:
        return await repo.get_by_id(self.user_id_from_tg(tg_id))

    async def get_chat_if_exists(
        self,
        *,
        tg_id: int,
        repo: ChatRepo,
    ) -> Chat | None:
        return await repo.get_by_id(self.chat_id_from_tg(tg_id))

    @staticmethod
    def user_id_from_tg(tg_id: int) -> UserId:
        return UserId(UUID(str(uuid5(NAMESPACE_DNS, f"user:{tg_id}"))))

    @staticmethod
    def chat_id_from_tg(tg_id: int) -> ChatId:
        return ChatId(UUID(str(uuid5(NAMESPACE_DNS, f"chat:{tg_id}"))))
