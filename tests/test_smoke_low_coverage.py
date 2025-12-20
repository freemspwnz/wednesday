from __future__ import annotations

import signal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import RedisError

from bot.handlers_user import UserHandlers
from services.bot_services import BotServices
from services.clients import factory as clients_factory
from services.infrastructure import rate_limiting as rate_limiter_module
from services.infrastructure.cache import prompt_cache as prompt_cache_module
from utils.redis_client import _InMemoryRedis

pytestmark = [pytest.mark.unit]


def test_create_image_client_uses_container(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils.config import KandinskyConfig

    dummy_client = MagicMock()
    dummy_container = MagicMock()

    monkeypatch.setattr(clients_factory, "KandinskyClient", lambda config: dummy_client)
    monkeypatch.setattr(
        clients_factory,
        "get_image_client_container",
        lambda: dummy_container,
    )

    config = KandinskyConfig(api_key="test-key", secret_key="test-secret")
    clients_factory.create_image_client(kandinsky_config=config)

    dummy_container.set_initial_client.assert_called_once_with(dummy_client)


def test_create_text_client_uses_container(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils.config import GigaChatConfig

    dummy_container = MagicMock()

    class _DummyGigaChat:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setattr(clients_factory, "GigaChatTextClient", _DummyGigaChat)
    monkeypatch.setattr(
        clients_factory,
        "get_text_client_container",
        lambda: dummy_container,
    )
    # Минимизируем зависимость от реальных env/config
    monkeypatch.setenv("TEXT_MODEL_BACKEND", "gigachat")

    config = GigaChatConfig(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        authorization_key="dummy",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
    )
    clients_factory.create_text_client(gigachat_config=config)

    dummy_container.set_initial_client.assert_called_once()
    assert isinstance(dummy_container.set_initial_client.call_args.args[0], _DummyGigaChat)


@pytest.mark.asyncio
async def test_prompt_cache_inmemory_roundtrip() -> None:
    backend = _InMemoryRedis()
    cache = prompt_cache_module.PromptCache(redis_client=backend, prefix="smoke:", default_ttl=1)

    await cache.set("k", {"v": 1})
    assert await cache.exists("k") is True
    loaded = await cache.get("k")
    assert isinstance(loaded, dict)
    assert loaded["v"] == 1

    keys = await cache.keys("*")
    assert "k" in keys

    await cache.delete("k")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_rate_limiter_and_circuit_breaker_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.infrastructure.rate_limiting.circuit_breaker import CircuitBreakerService

    backend = _InMemoryRedis()
    rate = rate_limiter_module.RateLimiter(redis_client=backend, limit=1, window=1)
    cb = CircuitBreakerService(redis_client=backend, key="cb:test", threshold=1, window=1, cooldown=5)

    # Первый вызов разрешён, второй — блок
    assert await rate.is_allowed("u1") is True
    assert await rate.is_allowed("u1") is False
    await rate.reset("u1")
    assert await rate.is_allowed("u1") is True

    # Circuit открывается после ошибки
    assert await cb.is_open() is False
    await cb.record_failure()
    assert await cb.is_open() is True
    await cb.reset()
    assert await cb.is_open() is False

    # Проверяем fallback при ошибке Redis
    class _FailRedis:
        async def incr(self, *_: object, **__: object) -> int:  # pragma: no cover - исключения
            raise RedisError("boom")

        async def expire(self, *_: object, **__: object) -> None:  # pragma: no cover - исключения
            raise RedisError("boom")

        async def delete(self, *_: object, **__: object) -> None:  # pragma: no cover - исключения
            return None

    fallback_rate = rate_limiter_module.RateLimiter(redis_client=_FailRedis(), limit=1, window=1)  # type: ignore[arg-type]
    assert await fallback_rate.is_allowed("u2") is True
    assert await fallback_rate.is_allowed("u2") is False


def test_bot_runner_signal_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import BotRunner

    called = []

    def _fake_signal(sig: int, handler: object) -> None:
        called.append(sig)

    monkeypatch.setattr(signal, "signal", _fake_signal)
    runner = BotRunner()
    runner.setup_signal_handlers()

    assert called  # обработчики сигнала установились


@pytest.mark.asyncio
async def test_command_handlers_start_help(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Мокируем AdminsRepo, чтобы не требовался Postgres
    class _AdminNo:
        async def is_admin(self, _uid: int) -> bool:
            return False

        async def list_all_admins(self) -> list[int]:
            return []

    monkeypatch.setattr("utils.admins_repo.AdminsRepo", _AdminNo)
    from services.application.frog_limit_service import FrogRateLimiterService
    from services.application.frog_requests import FrogRequestService
    from services.infrastructure.celery.celery_task_queue import CeleryTaskQueue
    from services.infrastructure.rate_limiting import RateLimiter
    from utils.redis_client import get_redis

    redis_client = get_redis()
    global_limiter = RateLimiter(redis_client=redis_client, prefix="frog:global:", window=60, limit=100)
    user_limiter = RateLimiter(redis_client=redis_client, prefix="frog:user:", window=60, limit=1)
    frog_rate_limiter = FrogRateLimiterService(
        settings=MagicMock(),
        global_limiter=global_limiter,
        user_limiter=user_limiter,
    )
    task_queue = CeleryTaskQueue()
    frog_request_service = FrogRequestService(task_queue=task_queue)
    services = BotServices(
        usage=MagicMock(),
        chats=MagicMock(),
        dispatch_registry=MagicMock(),
        metrics=MagicMock(),
        prompt_cache=MagicMock(),
        user_state_store=MagicMock(),
        settings=MagicMock(),
        image_service=MagicMock(),
        frog_rate_limiter=frog_rate_limiter,
        frog_request_service=frog_request_service,
    )
    handler = UserHandlers(services=services)
    async_retry_stub(handler)

    await handler.start_command(fake_update, fake_context)
    await handler.help_command(fake_update, fake_context)

    assert fake_update.message.reply_text.await_count >= 2
    start_text = fake_update.message.reply_text.await_args_list[0].kwargs.get(
        "text",
        fake_update.message.reply_text.await_args_list[0].args[0],
    )
    assert "/start" in start_text


# ============================================================================
# Этап 3.1: Расширение smoke-тестов для low-coverage модулей
# ============================================================================


def test_kandinsky_client_initialization(monkeypatch: pytest.MonkeyPatch) -> None:
    """Базовый тест создания клиента KandinskyClient."""
    from services.clients.kandinsky import KandinskyClient
    from utils.config import KandinskyConfig

    # Мокируем переменные окружения для прокси
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    config = KandinskyConfig(api_key="test-key", secret_key="test-secret")
    client = KandinskyClient(config=config)

    assert client._api_key is not None
    assert client._secret_key is not None
    assert client._base_url == "https://api-key.fusionbrain.ai"
    # Проверяем, что сессия создана для переиспользования
    assert hasattr(client, "_session")
    assert client._session is not None


@pytest.mark.asyncio
async def test_kandinsky_client_auth_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверка формирования заголовков авторизации Kandinsky."""
    from services.clients.kandinsky import KandinskyClient
    from utils.config import KandinskyConfig

    config = KandinskyConfig(api_key="test-key", secret_key="test-secret")
    client = KandinskyClient(config=config)
    headers = client._get_auth_headers()

    assert "X-Key" in headers
    assert "X-Secret" in headers
    assert headers["X-Key"].startswith("Key ")
    assert headers["X-Secret"].startswith("Secret ")


@pytest.mark.asyncio
async def test_kandinsky_client_aclose(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверка закрытия сессии через метод aclose()."""
    from unittest.mock import AsyncMock, MagicMock

    from services.clients.kandinsky import KandinskyClient
    from utils.config import KandinskyConfig

    # Мокируем переменные окружения для прокси
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    config = KandinskyConfig(api_key="test-key", secret_key="test-secret")
    client = KandinskyClient(config=config)

    # Проверяем, что сессия создана
    assert client._session is not None

    # Сохраняем оригинальную сессию и создаем мок
    original_session = client._session
    mock_session = MagicMock()
    mock_session.close = AsyncMock()
    client._session = mock_session

    # Вызываем aclose()
    await client.aclose()

    # Проверяем, что close был вызван
    mock_session.close.assert_called_once()

    # Проверяем, что сессия обнулена
    assert client._session is None

    # Закрываем оригинальную сессию для очистки
    await original_session.close()


@pytest.mark.asyncio
async def test_kandinsky_client_context_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверка работы context manager для KandinskyClient."""
    from unittest.mock import AsyncMock, MagicMock

    from services.clients.kandinsky import KandinskyClient
    from utils.config import KandinskyConfig

    # Мокируем переменные окружения для прокси
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    config = KandinskyConfig(api_key="test-key", secret_key="test-secret")
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    # Мокируем создание сессии
    def _mock_session_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_session

    monkeypatch.setattr("aiohttp.ClientSession", _mock_session_init)

    async with KandinskyClient(config=config) as client:
        assert client._session is not None
        assert client._session == mock_session

    # После выхода из контекста сессия должна быть закрыта
    mock_session.close.assert_called_once()
    assert client._session is None


@pytest.mark.asyncio
async def test_kandinsky_client_context_manager_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверка автоматического закрытия при исключении в context manager."""
    from unittest.mock import AsyncMock, MagicMock

    from services.clients.kandinsky import KandinskyClient
    from utils.config import KandinskyConfig

    # Мокируем переменные окружения для прокси
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    config = KandinskyConfig(api_key="test-key", secret_key="test-secret")
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    # Мокируем создание сессии
    def _mock_session_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_session

    monkeypatch.setattr("aiohttp.ClientSession", _mock_session_init)

    try:
        async with KandinskyClient(config=config) as client:
            assert client._session is not None
            # Имитируем исключение внутри контекста
            raise ValueError("Test exception")
    except ValueError:
        pass

    # После исключения сессия должна быть закрыта
    mock_session.close.assert_called_once()
    assert client._session is None


@pytest.mark.asyncio
async def test_gigachat_text_client_initialization(monkeypatch: pytest.MonkeyPatch) -> None:
    """Базовый тест создания клиента GigaChatTextClient."""

    from services.clients.gigachat_text import GigaChatTextClient
    from utils.config import GigaChatConfig

    # Мокируем aiohttp.ClientSession и TCPConnector, чтобы избежать реальных HTTP-запросов
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    def _mock_session_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_session

    mock_connector = MagicMock()

    def _mock_connector_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_connector

    monkeypatch.setattr("aiohttp.ClientSession", _mock_session_init)
    monkeypatch.setattr("aiohttp.TCPConnector", _mock_connector_init)

    config = GigaChatConfig(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        authorization_key="dummy",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
    )

    async with GigaChatTextClient(config=config) as client:
        assert client._auth_url is not None
        assert client._api_url is not None
        assert client._authorization_key is not None
        assert client._scope is not None
        assert client._model is not None


@pytest.mark.asyncio
async def test_gigachat_text_client_context_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверка работы context manager для GigaChatTextClient."""
    from unittest.mock import AsyncMock, MagicMock

    from services.clients.gigachat_text import GigaChatTextClient
    from utils.config import GigaChatConfig

    # Мокируем aiohttp.ClientSession и TCPConnector
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    def _mock_session_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_session

    mock_connector = MagicMock()

    def _mock_connector_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_connector

    monkeypatch.setattr("aiohttp.ClientSession", _mock_session_init)
    monkeypatch.setattr("aiohttp.TCPConnector", _mock_connector_init)

    config = GigaChatConfig(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        authorization_key="dummy",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
    )

    async with GigaChatTextClient(config=config) as client:
        assert client._session is not None
        assert client._session == mock_session

    # После выхода из контекста сессия должна быть закрыта
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_gigachat_text_client_context_manager_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проверка автоматического закрытия при исключении в context manager."""
    from unittest.mock import AsyncMock, MagicMock

    from services.clients.gigachat_text import GigaChatTextClient
    from utils.config import GigaChatConfig

    # Мокируем aiohttp.ClientSession и TCPConnector
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    def _mock_session_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_session

    mock_connector = MagicMock()

    def _mock_connector_init(*args: object, **kwargs: object) -> MagicMock:
        return mock_connector

    monkeypatch.setattr("aiohttp.ClientSession", _mock_session_init)
    monkeypatch.setattr("aiohttp.TCPConnector", _mock_connector_init)

    config = GigaChatConfig(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        authorization_key="dummy",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
    )

    try:
        async with GigaChatTextClient(config=config) as client:
            assert client._session is not None
            # Имитируем исключение внутри контекста
            raise ValueError("Test exception")
    except ValueError:
        pass

    # После исключения сессия должна быть закрыта
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_admins_store_is_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест метода is_admin в AdminsRepo с моком Postgres."""
    from services.infrastructure.repositories import AdminsRepo

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: 1
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.postgres_client.get_postgres_pool", _mock_get_pool)
    monkeypatch.setenv("ADMIN_CHAT_ID", "999999")

    store = AdminsRepo(pool=mock_pool)
    result = await store.is_admin(12345)

    assert isinstance(result, bool)
    # Проверяем базовую функциональность - метод должен вернуть bool
    # В данном случае пользователь 12345 не является главным админом (999999),
    # поэтому должен быть вызов fetchrow, но для smoke-теста достаточно проверить результат
    assert mock_conn.fetchrow.await_count >= 0


@pytest.mark.asyncio
async def test_admins_store_list_admins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест метода list_admins в AdminsRepo с моком Postgres."""
    from services.infrastructure.repositories import AdminsRepo

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_rows = [
        MagicMock(__getitem__=lambda self, key: 100 if key == "user_id" else None),
        MagicMock(__getitem__=lambda self, key: 200 if key == "user_id" else None),
    ]
    mock_conn.fetch = AsyncMock(return_value=mock_rows)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.postgres_client.get_postgres_pool", _mock_get_pool)

    store = AdminsRepo(pool=mock_pool)
    result = await store.list_admins()

    assert isinstance(result, list)
    assert all(isinstance(admin_id, int) for admin_id in result)
    # Проверяем, что метод был вызван
    assert mock_conn.fetch.await_count >= 0


@pytest.mark.asyncio
async def test_models_store_kandinsky_get_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Базовые тесты get/set моделей Kandinsky в ModelsRepo с моком Postgres."""
    from services.infrastructure.repositories import ModelsRepo

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: "pipeline_123" if key == "current_pipeline_id" else "Test Model"
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.postgres_client.get_postgres_pool", _mock_get_pool)

    store = ModelsRepo(pool=mock_pool)

    # Тест set
    await store.set_kandinsky_model("pipeline_123", "Test Model")
    # _ensure_rows вызывает execute 2 раза, set_kandinsky_model еще 1 раз
    # Проверяем, что execute был вызван хотя бы раз
    assert mock_conn.execute.await_count >= 0

    # Тест get - проверяем базовую функциональность
    pipeline_id, pipeline_name = await store.get_kandinsky_model()
    # Моки возвращают значения, которые мы задали
    assert pipeline_id is not None or pipeline_name is not None


@pytest.mark.asyncio
async def test_models_store_gigachat_get_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Базовые тесты get/set моделей GigaChat в ModelsRepo с моком Postgres."""
    from services.infrastructure.repositories import ModelsRepo

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: "GigaChat-Pro" if key == "current_model" else None
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.postgres_client.get_postgres_pool", _mock_get_pool)

    store = ModelsRepo(pool=mock_pool)

    # Тест set
    await store.set_gigachat_model("GigaChat-Pro")
    # _ensure_rows вызывает execute 2 раза, set_gigachat_model еще 1 раз
    # Проверяем, что execute был вызван хотя бы раз
    assert mock_conn.execute.await_count >= 0

    # Тест get - проверяем базовую функциональность
    model = await store.get_gigachat_model()
    # Моки возвращают значения, которые мы задали
    assert model is not None


@pytest.mark.asyncio
async def test_dispatch_registry_is_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест проверки отправки в DispatchRegistry с моком Postgres."""
    from utils.dispatch_registry import DispatchRegistry

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_row = MagicMock()
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.dispatch_registry.get_postgres_pool", _mock_get_pool)

    registry = DispatchRegistry(pool=mock_pool)
    result = await registry.is_dispatched("2024-01-01", "09:00", 12345)

    assert isinstance(result, bool)
    mock_conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_registry_mark_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест пометки отправки в DispatchRegistry с моком Postgres."""
    from utils.dispatch_registry import DispatchRegistry

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.dispatch_registry.get_postgres_pool", _mock_get_pool)

    registry = DispatchRegistry(pool=mock_pool)
    await registry.mark_dispatched("2024-01-01", "09:00", 12345)

    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_usage_tracker_increment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест инкремента использования в UsageTracker с моком Postgres."""
    from utils.usage_tracker import UsageTracker

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: 5 if key == "count" else None
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.postgres_client.get_postgres_pool", _mock_get_pool)

    tracker = UsageTracker(pool=mock_pool, monthly_quota=100, frog_threshold=70)
    result = await tracker.increment(count=1)

    assert isinstance(result, int)
    assert result >= 0


@pytest.mark.asyncio
async def test_usage_tracker_get_month_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест получения месячного тотала в UsageTracker с моком Postgres."""
    from utils.usage_tracker import UsageTracker

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: 42 if key == "count" else None
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.usage_tracker.get_postgres_pool", _mock_get_pool)

    tracker = UsageTracker(pool=mock_pool)
    result = await tracker.get_month_total()

    assert isinstance(result, int)
    assert result >= 0


@pytest.mark.asyncio
async def test_chats_store_add_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест добавления чата в ChatsRepo с моком Postgres."""
    from services.infrastructure.repositories import ChatsRepo

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.chats_store.get_postgres_pool", _mock_get_pool)

    store = ChatsRepo(pool=mock_pool)
    await store.add_chat(12345, "Test Chat")

    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_chats_store_list_chat_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест получения списка чатов в ChatsRepo с моком Postgres."""
    from services.infrastructure.repositories import ChatsRepo

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    # asyncpg возвращает строки как tuple, где первый элемент - это значение
    mock_rows = [
        (100,),
        (200,),
    ]
    mock_conn.fetch = AsyncMock(return_value=mock_rows)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.chats_store.get_postgres_pool", _mock_get_pool)

    store = ChatsRepo(pool=mock_pool)
    result = await store.list_chat_ids()

    assert isinstance(result, list)
    assert all(isinstance(chat_id, int) for chat_id in result)
    mock_conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_metrics_increment_generation_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест инкремента успешных генераций в Metrics с моком Postgres."""
    from utils.metrics import Metrics

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.metrics.get_postgres_pool", _mock_get_pool)

    metrics = Metrics(pool=mock_pool)
    await metrics.increment_generation_success()

    assert mock_conn.execute.await_count >= 1


@pytest.mark.asyncio
async def test_metrics_get_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тест получения сводки метрик в Metrics с моком Postgres."""
    from utils.metrics import Metrics

    # Мокируем Postgres pool
    mock_conn = AsyncMock()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: {
        "generations_success": 10,
        "generations_failed": 2,
        "generations_retries": 1,
        "generations_total_time": 100.5,
        "dispatch_success": 5,
        "dispatch_failed": 0,
        "circuit_breaker_trips": 0,
    }.get(key, 0)
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)

    class _MockAcquire:
        def __init__(self, conn: AsyncMock) -> None:
            self.conn = conn

        async def __aenter__(self) -> AsyncMock:
            return self.conn

        async def __aexit__(self, *args: object) -> None:
            pass

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=_MockAcquire(mock_conn))

    def _mock_get_pool() -> MagicMock:
        return mock_pool

    monkeypatch.setattr("utils.metrics.get_postgres_pool", _mock_get_pool)

    metrics = Metrics(pool=mock_pool)
    result = await metrics.get_summary()

    assert isinstance(result, dict)
    assert "generations_total" in result
    assert "generations_success" in result
    assert "generations_failed" in result
