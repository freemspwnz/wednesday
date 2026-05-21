"""Тесты RegistrationService и RegistrationUseCase."""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, Mock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.dto import ChatContext, UserContext
from app.services.registration_srv import RegistrationService
from app.use_cases.registration_uc import RegistrationUseCase
from domain.chat import Chat, ChatId, ChatProfile, ChatScheduleSet, ChatType, Weekday
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole, UserSubscription


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def _mk_logger() -> Mock:
    logger = Mock()
    logger.bind.return_value = logger
    return logger


class _CacheRegistry:
    def __init__(self) -> None:
        self.user = AsyncMock()
        self.chat = AsyncMock()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_user_returns_existing_and_updates_seen() -> None:
    service = RegistrationService(logger=_mk_logger())
    repo = AsyncMock()
    existing = User.register(
        id=UserId(UUID(int=10)),
        profile=UserProfile(telegram_id=999, is_bot=False, first_name=NonEmptyStr("A")),
        role=UserRole.USER,
        subscription=UserSubscription.free(dt(9)),
        now=dt(9),
    )
    repo.get_by_id.return_value = existing
    dto = UserContext(tg_id=999, is_bot=False, first_name=NonEmptyStr("A"))

    result = await service.get_or_create_user(dto=dto, repo=repo)

    assert result is existing
    repo.get_by_id.assert_awaited_once()
    repo.save.assert_awaited_once_with(existing)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_user_creates_new_entity() -> None:
    service = RegistrationService(logger=_mk_logger())
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    dto = UserContext(
        tg_id=111,
        is_bot=False,
        first_name=NonEmptyStr("John"),
        role=UserRole.ADMIN,
        has_tg_premium=True,
    )

    result = await service.get_or_create_user(dto=dto, repo=repo)

    assert isinstance(result, User)
    assert result.profile.telegram_id == 111
    assert result.role == UserRole.ADMIN
    assert result.profile.has_tg_premium is True
    repo.save.assert_awaited_once_with(result)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_chat_returns_existing() -> None:
    service = RegistrationService(logger=_mk_logger())
    repo = AsyncMock()
    existing = Chat.register(
        id=ChatId(UUID(int=20)),
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=222),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC"), weekday=Weekday.WEDNESDAY),
        at=dt(10),
    )
    repo.get_by_id.return_value = existing
    dto = ChatContext(tg_id=222, type=ChatType.PRIVATE)

    result = await service.get_or_create_chat(dto=dto, repo=repo)

    assert result is existing
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_chat_creates_new_entity() -> None:
    service = RegistrationService(logger=_mk_logger())
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    dto = ChatContext(
        tg_id=-100123,
        type=ChatType.GROUP,
        title="Ops",
        username="ops_chat",
        timezone=ZoneInfo("UTC"),
        weekday=Weekday.FRIDAY,
    )

    result = await service.get_or_create_chat(dto=dto, repo=repo)

    assert isinstance(result, Chat)
    assert result.profile.telegram_id == -100123
    assert result.profile.type == ChatType.GROUP
    assert result.schedules.weekday == Weekday.FRIDAY
    repo.save.assert_awaited_once_with(result)


@pytest.mark.unit
def test_service_id_generation_is_deterministic() -> None:
    service = RegistrationService(logger=_mk_logger())
    assert service.user_id_from_tg(1) == service.user_id_from_tg(1)
    assert service.chat_id_from_tg(2) == service.chat_id_from_tg(2)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_user_if_exists_returns_none_when_missing() -> None:
    service = RegistrationService(logger=_mk_logger())
    repo = AsyncMock()
    repo.get_by_id.return_value = None

    result = await service.get_user_if_exists(tg_id=999, repo=repo)

    assert result is None
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_chat_if_exists_returns_entity_without_save() -> None:
    service = RegistrationService(logger=_mk_logger())
    repo = AsyncMock()
    existing = Chat.register(
        id=ChatId(UUID(int=21)),
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=333),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC"), weekday=Weekday.WEDNESDAY),
        at=dt(10),
    )
    repo.get_by_id.return_value = existing

    result = await service.get_chat_if_exists(tg_id=333, repo=repo)

    assert result is existing
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reg_user_returns_cached_value_without_uow() -> None:
    logger = Mock()
    logger.bind.return_value = logger
    cache = _CacheRegistry()
    uow = AsyncMock()
    service = AsyncMock()
    uc = RegistrationUseCase(uow=uow, reg_service=service, cache_registry=cache, logger=logger)

    dto = UserContext(tg_id=42, is_bot=False, first_name=NonEmptyStr("A"))
    cache.user.get_by_id.return_value = dto

    got = await uc.reg_user(dto=dto)

    assert got is dto
    cache.user.get_by_id.assert_awaited_once_with(42)
    assert not service.get_or_create_user.await_args_list


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reg_chat_loads_via_service_and_caches() -> None:
    logger = Mock()
    logger.bind.return_value = logger
    cache = _CacheRegistry()
    service = AsyncMock()

    class _Uow:
        def __init__(self) -> None:
            self.users = AsyncMock()
            self.chats = AsyncMock()

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

    uc = RegistrationUseCase(
        uow=_Uow(),
        reg_service=service,
        cache_registry=cache,
        logger=logger,
    )

    dto = ChatContext(tg_id=-100, type=ChatType.GROUP, title="T")
    cache.chat.get_by_id.return_value = None
    domain_chat = Chat.register(
        id=ChatId(UUID(int=7)),
        profile=ChatProfile(type=ChatType.GROUP, telegram_id=-100, title="T"),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC"), weekday=Weekday.WEDNESDAY),
        at=dt(10),
    )
    service.get_or_create_chat.return_value = domain_chat

    got = await uc.reg_chat(dto=dto)

    assert isinstance(got, ChatContext)
    assert got.tg_id == -100
    cache.chat.set.assert_awaited_once_with(domain_chat)
    service.get_or_create_chat.assert_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reg_chat_returns_cached_value_without_uow() -> None:
    logger = Mock()
    logger.bind.return_value = logger
    cache = _CacheRegistry()
    uow = AsyncMock()
    service = AsyncMock()
    uc = RegistrationUseCase(uow=uow, reg_service=service, cache_registry=cache, logger=logger)

    dto = ChatContext(tg_id=-100, type=ChatType.GROUP, title="T")
    cache.chat.get_by_id.return_value = dto

    got = await uc.reg_chat(dto=dto)

    assert got is dto
    cache.chat.get_by_id.assert_awaited_once_with(-100)
    assert not service.get_or_create_chat.await_args_list


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_user_by_tg_id_returns_none_without_create() -> None:
    logger = Mock()
    logger.bind.return_value = logger
    cache = _CacheRegistry()
    service = AsyncMock()

    class _Uow:
        def __init__(self) -> None:
            self.users = AsyncMock()
            self.chats = AsyncMock()

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

    uc = RegistrationUseCase(
        uow=_Uow(),
        reg_service=service,
        cache_registry=cache,
        logger=logger,
    )
    cache.user.get_by_id.return_value = None
    service.get_user_if_exists.return_value = None

    got = await uc.find_user_by_tg_id(tg_id=404)

    assert got is None
    service.get_user_if_exists.assert_awaited_once()
    service.get_or_create_user.assert_not_awaited()
    cache.user.set.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_chat_by_tg_id_loads_from_db_without_create() -> None:
    logger = Mock()
    logger.bind.return_value = logger
    cache = _CacheRegistry()
    service = AsyncMock()

    class _Uow:
        def __init__(self) -> None:
            self.users = AsyncMock()
            self.chats = AsyncMock()

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            return None

    uc = RegistrationUseCase(
        uow=_Uow(),
        reg_service=service,
        cache_registry=cache,
        logger=logger,
    )
    cache.chat.get_by_id.return_value = None
    domain_chat = Chat.register(
        id=ChatId(UUID(int=8)),
        profile=ChatProfile(type=ChatType.GROUP, telegram_id=-200, title="G"),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC"), weekday=Weekday.WEDNESDAY),
        at=dt(10),
    )
    service.get_chat_if_exists.return_value = domain_chat

    got = await uc.find_chat_by_tg_id(tg_id=-200)

    assert isinstance(got, ChatContext)
    assert got.tg_id == -200
    service.get_chat_if_exists.assert_awaited_once()
    service.get_or_create_chat.assert_not_awaited()
    cache.chat.set.assert_awaited_once_with(domain_chat)
