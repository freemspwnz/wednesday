from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, exists, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    SQLAAggregateMappingError,
    SQLADataIntegrityError,
    SQLARepositoryError,
    UnexpectedSQLAError,
)
from domain.chat import (
    ActiveState,
    Chat,
    ChatId,
    ChatProfile,
    ChatRepo,
    ChatSchedule,
    ChatScheduleSet,
    ChatType,
    InactiveState,
    Weekday,
)
from domain.kernel.vo import AwareDatetime

from ..models import ChatORM, ChatProfileORM, ChatScheduleSettingsORM, ChatScheduleSlotORM, ChatStateORM


class SQLAChatRepo(ChatRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, chat_id: ChatId) -> Chat | None:
        try:
            stmt = select(ChatORM).where(ChatORM.id == chat_id.value)
            result = await self._session.execute(stmt)
            orm_chat = result.scalar_one_or_none()
            if orm_chat is None:
                return None
            return _chat_from_orm(orm_chat)
        except ValueError as exc:
            raise SQLAAggregateMappingError(
                "Failed to map ORM chat aggregate.",
                operation="get_by_id",
                entity="chat",
                entity_id=chat_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to load chat aggregate.",
                operation="get_by_id",
                entity="chat",
                entity_id=chat_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while reading chat aggregate.") from exc

    async def save(self, chat: Chat) -> None:
        try:
            await self._session.execute(
                insert(ChatORM)
                .values(
                    id=chat.id.value,
                    created_at=chat.created_at.value,
                    updated_at=chat.updated_at.value,
                )
                .on_conflict_do_update(
                    index_elements=[ChatORM.id],
                    set_={"updated_at": chat.updated_at.value},
                )
            )

            await self._session.execute(
                insert(ChatProfileORM)
                .values(
                    chat_id=chat.id.value,
                    telegram_id=chat.profile.telegram_id,
                    chat_type=chat.profile.type.value,
                    title=chat.profile.title,
                    username=chat.profile.username,
                )
                .on_conflict_do_update(
                    index_elements=[ChatProfileORM.chat_id],
                    set_={
                        "telegram_id": chat.profile.telegram_id,
                        "chat_type": chat.profile.type.value,
                        "title": chat.profile.title,
                        "username": chat.profile.username,
                    },
                )
            )

            is_active = isinstance(chat.state, ActiveState)
            await self._session.execute(
                insert(ChatStateORM)
                .values(
                    chat_id=chat.id.value,
                    is_active=is_active,
                )
                .on_conflict_do_update(
                    index_elements=[ChatStateORM.chat_id],
                    set_={"is_active": is_active},
                )
            )

            await self._session.execute(
                insert(ChatScheduleSettingsORM)
                .values(
                    chat_id=chat.id.value,
                    timezone=str(chat.schedules.timezone),
                    weekday=int(chat.schedules.weekday),
                )
                .on_conflict_do_update(
                    index_elements=[ChatScheduleSettingsORM.chat_id],
                    set_={
                        "timezone": str(chat.schedules.timezone),
                        "weekday": int(chat.schedules.weekday),
                    },
                )
            )

            desired_slots = sorted(
                {(schedule.hour, schedule.minute) for schedule in chat.schedules.schedules},
                key=lambda x: (x[0], x[1]),
            )
            if desired_slots:
                await self._session.execute(
                    delete(ChatScheduleSlotORM).where(
                        and_(
                            ChatScheduleSlotORM.chat_id == chat.id.value,
                            tuple_(ChatScheduleSlotORM.hour, ChatScheduleSlotORM.minute).not_in(desired_slots),
                        ),
                    )
                )
                await self._session.execute(
                    insert(ChatScheduleSlotORM)
                    .values([
                        {
                            "chat_id": chat.id.value,
                            "hour": hour,
                            "minute": minute,
                        }
                        for hour, minute in desired_slots
                    ])
                    .on_conflict_do_nothing(
                        index_elements=[
                            ChatScheduleSlotORM.chat_id,
                            ChatScheduleSlotORM.hour,
                            ChatScheduleSlotORM.minute,
                        ]
                    )
                )
            else:
                await self._session.execute(
                    delete(ChatScheduleSlotORM).where(ChatScheduleSlotORM.chat_id == chat.id.value)
                )
        except IntegrityError as exc:
            raise SQLADataIntegrityError(
                "Chat save violated database constraints.",
                operation="save",
                entity="chat",
                entity_id=chat.id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to persist chat aggregate.",
                operation="save",
                entity="chat",
                entity_id=chat.id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while saving chat aggregate.") from exc

    async def exists(self, chat_id: ChatId) -> bool:
        try:
            stmt = select(exists().where(ChatORM.id == chat_id.value))
            result = await self._session.execute(stmt)
            return bool(result.scalar_one())
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to check chat existence.",
                operation="exists",
                entity="chat",
                entity_id=chat_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while checking chat existence.") from exc


def _chat_from_orm(orm: ChatORM) -> Chat:
    if orm.profile is None or orm.state is None or orm.schedule_settings is None:
        raise ValueError(f"Incomplete chat aggregate loaded for chat_id={orm.id}")

    state = ActiveState() if orm.state.is_active else InactiveState()
    schedules = ChatScheduleSet(
        timezone=ZoneInfo(orm.schedule_settings.timezone),
        weekday=Weekday(orm.schedule_settings.weekday),
        schedules=tuple(
            sorted(
                (ChatSchedule(hour=schedule.hour, minute=schedule.minute) for schedule in orm.schedule_slots),
                key=lambda s: (s.hour, s.minute),
            )
        ),
    )
    profile = ChatProfile(
        type=ChatType(orm.profile.chat_type),
        telegram_id=orm.profile.telegram_id,
        title=orm.profile.title,
        username=orm.profile.username,
    )
    return Chat.restore(
        id=ChatId(orm.id),
        profile=profile,
        state=state,
        schedules=schedules,
        created_at=AwareDatetime.from_datetime(orm.created_at),
        updated_at=AwareDatetime.from_datetime(orm.updated_at),
    )
