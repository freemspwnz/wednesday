"""Tests for RegistrationService and RegistrationUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from dom.user.factories import FakeModelCatalog, FakeSubscriptionCatalog, default_settings, subscription_free

from app.dto import ChatContext
from app.services.registration import RegistrationService
from app.use_cases.registration import RegistrationUseCase
from domain.chat import Chat, ChatId, ChatProfile, ChatScheduleSet, ChatType, Weekday
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole

from ..factories import FakeCacheRegistry, FakeUoW, mk_chat_context, mk_logger, mk_user_context


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def _profile(*, tg_id: int = 999, first_name: str = "A") -> UserProfile:
    return UserProfile(telegram_id=tg_id, is_bot=False, first_name=NonEmptyStr(first_name))


def _mk_service() -> RegistrationService:
    return RegistrationService(
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        logger=mk_logger(),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_user_returns_existing_and_updates_seen() -> None:
    service = _mk_service()
    repo = AsyncMock()
    existing = User.register(
        id=UserId(UUID(int=10)),
        profile=UserProfile(telegram_id=999, is_bot=False, first_name=NonEmptyStr("A")),
        role=UserRole.USER,
        subscription=subscription_free(dt(9)),
        settings=default_settings(),
        at=dt(9),
    )
    repo.get_by_id.return_value = existing

    result = await service.get_or_create_user(profile=_profile(tg_id=999), repo=repo)

    assert result is existing
    repo.get_by_id.assert_awaited_once()
    repo.save.assert_awaited_once_with(existing)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_user_creates_new_entity() -> None:
    service = _mk_service()
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    profile = UserProfile(
        telegram_id=111,
        is_bot=False,
        first_name=NonEmptyStr("John"),
        has_tg_premium=True,
    )

    result = await service.get_or_create_user(profile=profile, repo=repo)

    assert isinstance(result, User)
    assert result.profile.telegram_id == 111
    assert result.role == UserRole.USER
    assert result.profile.has_tg_premium is True
    assert str(result.settings.model) == "gigachat-2-lite"
    repo.save.assert_awaited_once_with(result)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_chat_returns_existing() -> None:
    service = _mk_service()
    repo = AsyncMock()
    existing = Chat.register(
        id=ChatId(UUID(int=20)),
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=222),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC"), weekday=Weekday.WEDNESDAY),
        at=dt(10),
    )
    repo.get_by_id.return_value = existing

    result = await service.get_or_create_chat(
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=222),
        repo=repo,
    )

    assert result is existing
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_get_or_create_chat_creates_new_entity() -> None:
    service = _mk_service()
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    profile = ChatProfile(
        type=ChatType.GROUP,
        telegram_id=-100123,
        title="Ops",
        username="ops_chat",
    )

    result = await service.get_or_create_chat(profile=profile, repo=repo)

    assert isinstance(result, Chat)
    assert result.profile.telegram_id == -100123
    assert result.profile.type == ChatType.GROUP
    assert result.schedules.weekday == Weekday.WEDNESDAY
    repo.save.assert_awaited_once_with(result)


@pytest.mark.unit
def test_service_id_generation_is_deterministic() -> None:
    service = _mk_service()
    assert service.user_id_from_tg(1) == service.user_id_from_tg(1)
    assert service.chat_id_from_tg(2) == service.chat_id_from_tg(2)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reg_user_returns_cached_value_without_uow() -> None:
    logger = mk_logger()
    cache = FakeCacheRegistry()
    uow = AsyncMock()
    service = AsyncMock()
    uc = RegistrationUseCase(uow=uow, service=service, cache=cache, logger=logger)

    profile = _profile(tg_id=42)
    cached = mk_user_context(user_id=42)
    cache.users.get_by_id.return_value = cached

    got = await uc.reg_user(profile=profile)

    assert got is cached
    cache.users.get_by_id.assert_awaited_once_with(42)
    assert not service.get_or_create_user.await_args_list


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reg_chat_loads_via_service_and_caches() -> None:
    logger = mk_logger()
    cache = FakeCacheRegistry()
    service = AsyncMock()

    uc = RegistrationUseCase(
        uow=FakeUoW(),
        service=service,
        cache=cache,
        logger=logger,
    )

    profile = ChatProfile(type=ChatType.GROUP, telegram_id=-100, title="T")
    cache.chats.get_by_id.return_value = None
    domain_chat = Chat.register(
        id=ChatId(UUID(int=7)),
        profile=ChatProfile(type=ChatType.GROUP, telegram_id=-100, title="T"),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC"), weekday=Weekday.WEDNESDAY),
        at=dt(10),
    )
    service.get_or_create_chat.return_value = domain_chat

    got = await uc.reg_chat(profile=profile)

    assert isinstance(got, ChatContext)
    assert got.tg_id == -100
    cache.chats.set.assert_awaited_once_with(domain_chat)
    service.get_or_create_chat.assert_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_reg_chat_returns_cached_value_without_uow() -> None:
    logger = mk_logger()
    cache = FakeCacheRegistry()
    uow = AsyncMock()
    service = AsyncMock()
    uc = RegistrationUseCase(uow=uow, service=service, cache=cache, logger=logger)

    profile = ChatProfile(type=ChatType.GROUP, telegram_id=-100, title="T")
    cached = mk_chat_context(tg_id=-100, chat_type=ChatType.GROUP)
    cache.chats.get_by_id.return_value = cached

    got = await uc.reg_chat(profile=profile)

    assert got is cached
    cache.chats.get_by_id.assert_awaited_once_with(-100)
    assert not service.get_or_create_chat.await_args_list


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_user_by_tg_id_returns_none_without_create() -> None:
    logger = mk_logger()
    cache = FakeCacheRegistry()
    service = AsyncMock()

    uc = RegistrationUseCase(
        uow=FakeUoW(),
        service=service,
        cache=cache,
        logger=logger,
    )
    cache.users.get_by_id.return_value = None
    service.get_user_if_exists.return_value = None

    got = await uc.find_user_by_tg_id(tg_id=404)

    assert got is None
    service.get_user_if_exists.assert_awaited_once()
    service.get_or_create_user.assert_not_awaited()
    cache.users.set.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_chat_by_tg_id_loads_from_db_without_create() -> None:
    logger = mk_logger()
    cache = FakeCacheRegistry()
    service = AsyncMock()

    uc = RegistrationUseCase(
        uow=FakeUoW(),
        service=service,
        cache=cache,
        logger=logger,
    )
    cache.chats.get_by_id.return_value = None
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
    cache.chats.set.assert_awaited_once_with(domain_chat)
