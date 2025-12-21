import asyncio
import importlib
import os
import sys
from collections.abc import AsyncIterator, Callable, Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

# Устанавливаем корень проекта в sys.path до всех импортов
# Это необходимо для unit-тестов, которые запускаются локально
if sys.path[0] != (repo_root := str(Path(__file__).parent.parent)):
    sys.path.insert(0, repo_root)

import pytest
import pytest_asyncio
from pytest import MonkeyPatch

# Импортируем fixtures для ожидания готовности Celery worker в E2E тестах
from tests.fixtures.celery_worker_ready import celery_worker_ready, celery_test_queues  # noqa: F401

_session_monkeypatch = MonkeyPatch()




def _is_running_in_docker() -> bool:
    """
    Определяет, запускаются ли тесты внутри Docker контейнера.

    Проверяет наличие файла /.dockerenv (создаётся Docker при запуске контейнера).

    Returns:
        True, если тесты запускаются в Docker контейнере, False иначе.
    """
    # Проверяем наличие файла /.dockerenv (самый надёжный способ определения Docker окружения)
    return Path("/.dockerenv").exists()


def _is_running_in_ci() -> bool:
    """
    Определяет, запускаются ли тесты в CI окружении.

    Проверяет переменные окружения, которые устанавливаются в CI:
    - GITHUB_ACTIONS (GitHub Actions)
    - CI (общая переменная для большинства CI систем)

    Returns:
        True, если тесты запускаются в CI, False иначе.
    """
    return os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"


_session_env_defaults = {
    "TELEGRAM_BOT_TOKEN": "session-test-token",
    "KANDINSKY_API_KEY": "session-test-api",
    "KANDINSKY_SECRET_KEY": "session-test-secret",
    "CHAT_ID": "999999",
    "ADMIN_CHAT_ID": "999998",
    # БД/Redis по умолчанию — для unit/integration без реальных сервисов
    "POSTGRES_USER": "test_user",
    "POSTGRES_PASSWORD": "test_password_ci_2025",
    "POSTGRES_DB": "wednesdaydb_test",
    # POSTGRES_HOST устанавливается условно: в Docker используем значение из окружения
    # (устанавливается docker-compose.test.yml), локально — localhost.
    # Это позволяет docker-compose.test.yml устанавливать правильный хост (postgres_test).
    "POSTGRES_PORT": "5432",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "REDIS_DB": "0",
    # Планировщик и базовые значения, не влияющие на сетевые адреса Postgres/Redis
    "SCHEDULER_SEND_TIMES": "09:00,12:00,18:00",
    "SCHEDULER_WEDNESDAY_DAY": "2",
    "SCHEDULER_TZ": "Europe/Moscow",
}

# Определяем POSTGRES_HOST в зависимости от окружения
if _is_running_in_docker():
    # В Docker контейнере: если POSTGRES_HOST уже установлен (из docker-compose.test.yml),
    # не перезаписываем его. Иначе устанавливаем postgres_test.
    if os.getenv("POSTGRES_HOST") is None:
        _session_env_defaults["POSTGRES_HOST"] = "postgres_test"
else:
    # Локально используем localhost
    _session_env_defaults["POSTGRES_HOST"] = "localhost"

for key, value in _session_env_defaults.items():
    # Не трогаем переменные, если они уже заданы извне (docker-compose/.env.test/CI)
    if os.getenv(key) is not None:
        continue
    # В Docker не перезаписываем POSTGRES_HOST, если compose уже выставил значение
    if key == "POSTGRES_HOST" and _is_running_in_docker() and os.getenv("POSTGRES_HOST") is not None:
        continue
    _session_monkeypatch.setenv(key, value)


@pytest.fixture(scope="session", autouse=True)
def session_env_defaults() -> Generator[None, None, None]:
    """Устанавливает обязательные переменные окружения до импорта модулей проекта."""
    yield
    _session_monkeypatch.undo()


class _InMemoryModelsRepo:
    """Простое хранилище моделей для тестов без файловой системы."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._gigachat_model: str | None = None
        self._gigachat_available: list[str] = []
        self._kandinsky_model: tuple[str | None, str | None] = (None, None)
        self._kandinsky_available: list[str] = []

    # GigaChat (async совместимый интерфейс)
    async def set_gigachat_model(self, model_name: str) -> None:
        self._gigachat_model = model_name

    async def get_gigachat_model(self) -> str | None:
        return self._gigachat_model

    async def set_gigachat_available_models(self, models: list[str]) -> None:
        self._gigachat_available = list(models)

    async def get_gigachat_available_models(self) -> list[str]:
        return list(self._gigachat_available)

    # Kandinsky (async совместимый интерфейс)
    async def set_kandinsky_model(self, pipeline_id: str, pipeline_name: str) -> None:
        self._kandinsky_model = (pipeline_id, pipeline_name)

    async def get_kandinsky_model(self) -> tuple[str | None, str | None]:
        return self._kandinsky_model

    async def set_kandinsky_available_models(self, models: list[Any] | list[str]) -> None:
        self._kandinsky_available = list(models) if models else []

    async def get_kandinsky_available_models(self) -> list[str]:
        return list(self._kandinsky_available)


@pytest.fixture(autouse=True)
def base_env(monkeypatch: Any, tmp_path_factory: Any) -> Generator[None, None, None]:
    """Гарантирует наличие обязательных переменных окружения и изолированных хранилищ."""
    env_defaults = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "KANDINSKY_API_KEY": "test-api",
        "KANDINSKY_SECRET_KEY": "test-secret",
        "CHAT_ID": "12345",
        "ADMIN_CHAT_ID": "54321",
        "GIGACHAT_AUTHORIZATION_KEY": "ZmFrZS1rZXk=",
        "GIGACHAT_SCOPE": "GIGACHAT_API_PERS",
        # Переменные планировщика для избежания вызовов load_dotenv() при инициализации SchedulerConfig
        "SCHEDULER_SEND_TIMES": "09:00,12:00,18:00",
        "SCHEDULER_WEDNESDAY_DAY": "2",
        "SCHEDULER_TZ": "Europe/Moscow",
    }
    for key, value in env_defaults.items():
        monkeypatch.setenv(key, value)
    yield


def _handle_postgres_error(exc: Exception, hint: str) -> None:
    """
    Обрабатывает ошибку подключения к PostgreSQL.

    В CI окружении вызывает pytest.fail(), локально - pytest.skip().

    Args:
        exc: Исключение, которое произошло при подключении.
        hint: Подсказка для пользователя.
    """
    error_msg = f"{hint}\nОшибка подключения: {exc!s}"
    if _is_running_in_ci():
        pytest.fail(error_msg)
    else:
        pytest.skip(error_msg)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Создаёт один глобальный event loop для всей сессии тестов.

    Используется для корректной работы session-scope async фикстур
    (например, async_postgres_pool, создаваемого один раз на сессию).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        asyncio.set_event_loop(None)
        loop.close()


@pytest_asyncio.fixture(scope="session")
async def async_postgres_pool() -> AsyncIterator[Any]:
    """
    Session-фикстура для создания пула соединений PostgreSQL на всю сессию тестов.

    Пул создаётся один раз на сессию и переиспользуется всеми тестами.
    Это более эффективно, чем создание пула для каждого теста.

    Используется минимальные параметры (min_size=1, max_size=2) для тестов.

    Если PostgreSQL недоступен, тесты с этой фикстурой будут пропущены (локально)
    или упадут с ошибкой (в CI) с понятным сообщением.
    """
    import asyncpg
    from infra.database.postgres_client import close_postgres_pool, init_postgres_pool
    from shared.config import config

    try:
        # Создаём пул с минимальными параметрами для тестов
        pool = await init_postgres_pool(min_size=1, max_size=2)
        # Убеждаемся в наличии схемы, используя созданный пул напрямую
        from infra.database.postgres_schema import _DDL_STATEMENTS
        async with pool.acquire() as conn:
            for stmt in _DDL_STATEMENTS:
                try:
                    await conn.execute(stmt)
                except Exception:  # pragma: no cover - защитное логирование
                    # Игнорируем ошибки создания таблиц (они могут уже существовать)
                    pass
        yield pool
    except (OSError, asyncpg.InvalidPasswordError, asyncpg.PostgresConnectionError) as exc:
        # Улучшенное сообщение об ошибке подключения
        postgres_host = config.postgres_host
        postgres_port = config.postgres_port
        is_docker = _is_running_in_docker()
        if is_docker:
            hint = (
                f"PostgreSQL недоступен по адресу {postgres_host}:{postgres_port}. "
                "Убедитесь, что контейнер postgres_test запущен и готов. "
                "Запустите `make test-up` для поднятия тестовых контейнеров."
            )
        else:
            hint = (
                f"PostgreSQL недоступен по адресу {postgres_host}:{postgres_port}. "
                "Убедитесь, что PostgreSQL запущен локально или запустите `make test-up` "
                "для поднятия тестовых контейнеров."
            )
        _handle_postgres_error(exc, hint)
    finally:
        # Закрываем пул после всех тестов
        # Используем wait_for для таймаута, чтобы не зависнуть на закрытии
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(close_postgres_pool(), timeout=5.0)
        except asyncio.TimeoutError:
            # Если закрытие пула занимает слишком много времени, продолжаем
            # (это может произойти, если есть зависшие соединения)
            pass
        except Exception:
            # Игнорируем ошибки при закрытии пула в teardown
            pass


@pytest_asyncio.fixture(scope="session")
async def _setup_test_postgres(async_postgres_pool: Any) -> AsyncIterator[None]:
    """
    Session-фикстура для инициализации тестовой БД Postgres.

    Подходит для integration/db тестов. В быстрых unit-прогонах не подключается.
    Использует session-пул из async_postgres_pool для оптимизации.

    Схема БД уже инициализируется в async_postgres_pool, поэтому эта фикстура
    просто гарантирует, что пул создан и готов к использованию.
    """
    # Схема БД уже инициализирована в async_postgres_pool, и пул готов к использованию.
    # Если пул не был создан, async_postgres_pool уже обработал ошибку.
    yield


@pytest_asyncio.fixture(scope="function")
async def cleanup_tables() -> AsyncIterator[None]:
    """
    Очищает таблицы между тестами для обеспечения изоляции.

    Используйте эту фикстуру в тестах, которые работают с PostgreSQL.
    Фикстура очищает все таблицы перед тестом, чтобы гарантировать изоляцию.

    Пример использования:
        @pytest.mark.asyncio
        async def test_something(cleanup_tables):
            # тест использует БД
    """
    # Используем session-пул напрямую, не вызывая _ensure_postgres_schema,
    # чтобы избежать проблем с event loops. Схема уже инициализирована в async_postgres_pool.
    from infra.database.postgres_client import get_postgres_pool

    try:
        pool = get_postgres_pool()
    except RuntimeError as exc:
        # Пул не инициализирован
        error_msg = (
            "Postgres pool не инициализирован. Запустите `make test-up` "
            "или экспортируйте корректные POSTGRES_* переменные."
        )
        _handle_postgres_error(exc, error_msg)

    # Очищаем таблицы ПЕРЕД тестом
    try:
        async with pool.acquire() as conn:
            # Используем CASCADE для удаления зависимостей (например, images зависит от prompts)
            await conn.execute(
                """
                TRUNCATE TABLE
                    images,
                    dispatch_registry,
                    prompts,
                    metrics_events,
                    chats,
                    admins,
                    usage_stats,
                    usage_settings,
                    metrics,
                    models_kandinsky,
                    models_gigachat
                RESTART IDENTITY CASCADE;
                """,
            )
    except Exception as exc:
        # Если таблицы не существуют, это может означать, что схема не инициализирована
        # В этом случае пробуем инициализировать схему
        try:
            from infra.database.postgres_schema import _DDL_STATEMENTS
            async with pool.acquire() as conn:
                for stmt in _DDL_STATEMENTS:
                    try:
                        await conn.execute(stmt)
                    except Exception:
                        pass
            # Повторяем попытку очистки после инициализации схемы
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    TRUNCATE TABLE
                        images,
                        dispatch_registry,
                        prompts,
                        metrics_events,
                        chats,
                        admins,
                        usage_stats,
                        usage_settings,
                        metrics,
                        models_kandinsky,
                        models_gigachat
                    RESTART IDENTITY CASCADE;
                    """,
                )
        except Exception:
            # Если всё ещё не получается, пропускаем очистку
            # (это может произойти, если схема действительно не инициализирована)
            pass

    yield


@pytest_asyncio.fixture(scope="function")
async def postgres_transaction(monkeypatch: Any) -> AsyncIterator[None]:
    """
    Использует транзакционный rollback для изоляции тестов.

    Эта фикстура создаёт транзакцию перед тестом и выполняет ROLLBACK после теста.
    Быстрее, чем TRUNCATE, но не подходит для тестов, которые проверяют commit'ы в БД.

    Используйте эту фикстуру для быстрых тестов без проверки commit'ов.
    Для тестов, которые проверяют commit'ы, используйте cleanup_tables.

    Пример использования:
        @pytest.mark.asyncio
        async def test_something(postgres_transaction):
            # тест использует БД, все изменения будут откачены после теста
    """
    import asyncpg
    from contextlib import asynccontextmanager
    from infra.database.postgres_client import get_postgres_pool

    # Используем session-пул напрямую, не вызывая _ensure_postgres_schema,
    # чтобы избежать проблем с event loops. Схема уже инициализирована в async_postgres_pool.
    try:
        pool = get_postgres_pool()
    except RuntimeError as exc:
        # Пул не инициализирован
        error_msg = (
            "Postgres pool не инициализирован. Запустите `make test-up` "
            "или экспортируйте корректные POSTGRES_* переменные."
        )
        _handle_postgres_error(exc, error_msg)

    # Получаем соединение и начинаем транзакцию
    transaction_conn = await pool.acquire()
    try:
        # Начинаем транзакцию ПЕРЕД патчем, чтобы все операции были в транзакции
        await transaction_conn.execute("BEGIN")

        # Патчим get_postgres_pool() чтобы возвращал патченный пул
        # Это позволяет использовать транзакцию во всех местах, где используется get_postgres_pool()
        from infra.database.postgres_client import get_postgres_pool

        class PatchedPool:
            """Обёртка над пулом, которая всегда возвращает транзакционное соединение."""

            def __init__(self, original_pool: Any, transaction_conn: Any) -> None:
                self._original_pool = original_pool
                self._transaction_conn = transaction_conn

            @asynccontextmanager
            async def acquire(self, *args: Any, **kwargs: Any) -> asyncpg.Connection:
                # Возвращаем то же соединение с транзакцией
                # Не освобождаем его, так как это делается в finally фикстуры
                yield self._transaction_conn

            async def release(self, connection: Any) -> None:
                # Игнорируем release для транзакционного соединения
                # Оно будет освобождено в finally фикстуры
                pass

            def __getattr__(self, name: str) -> Any:
                # Проксируем все остальные атрибуты к оригинальному пулу
                return getattr(self._original_pool, name)

        patched_pool = PatchedPool(pool, transaction_conn)
        # Сохраняем оригинальную функцию для восстановления
        original_get_pool = get_postgres_pool
        monkeypatch.setattr("utils.postgres_client.get_postgres_pool", lambda: patched_pool)

        yield
    finally:
        # Откатываем транзакцию
        try:
            await transaction_conn.execute("ROLLBACK")
        except Exception:
            # Игнорируем ошибки при rollback (например, если транзакция уже закрыта)
            pass
        finally:
            # Возвращаем соединение в пул
            await pool.release(transaction_conn)


@pytest.fixture(autouse=True)
def patch_models_repo(monkeypatch: Any, request: Any) -> Generator[None, None, None]:
    """
    Подменяет ModelsStore на простую in-memory реализацию.

    Исключает тесты из test_utils/test_models_store.py и интеграционные тесты,
    которые должны использовать реальный ModelsStore с Postgres.
    """
    from infra.repos import admins_repo as admins_repo_module
    from infra.repos import models_repo as models_repo_module

    # Не подменяем ModelsRepo для тестов, которые явно тестируют его или используют реальные хранилища
    test_file = request.node.fspath.strpath if hasattr(request.node, "fspath") else ""
    test_name = request.node.name if hasattr(request.node, "name") else ""

    markers = {marker.name for marker in request.node.iter_markers()}
    should_skip_patch = (
        "test_models_repo.py" in test_file
        or "integration_with_postgres_stores" in test_name
        or markers.intersection({"db", "integration", "e2e", "celery", "infra"})
    )

    if not should_skip_patch:
        monkeypatch.setattr(models_repo_module, "ModelsRepo", _InMemoryModelsRepo)

    # Создаём совместимый с AdminsRepo объект для тестов

    class _TestAdminsRepo:
        async def is_admin(self, user_id: int) -> bool:  # pragma: no cover - простая заглушка
            return False

        async def list_admins(self) -> list[int]:  # pragma: no cover - простая заглушка
            return []

        async def list_all_admins(self) -> list[int]:  # pragma: no cover - простая заглушка
            return []

    monkeypatch.setattr(admins_repo_module, "AdminsRepo", lambda *args, **kwargs: _TestAdminsRepo())
    yield


@pytest.fixture
def reload_config() -> Generator[Callable[[], Any], None, None]:
    """
    Возвращает функцию для повторной загрузки utils.config с актуальными env.
    После теста модуль очищается из sys.modules.
    """

    loaded_modules: list[Any] = []

    def _reload() -> Any:
        if "utils.config" in sys.modules:
            del sys.modules["utils.config"]
        module = importlib.import_module("utils.config")
        loaded_modules.append(module)
        return module

    try:
        yield _reload
    finally:
        if "utils.config" in sys.modules:
            del sys.modules["utils.config"]
        # пересоздаем модуль для других тестов с дефолтным окружением
        importlib.import_module("utils.config")


@pytest.fixture
def fake_update() -> Any:
    """Создает простую структуру Update с асинхронным reply_text."""
    status_message = SimpleNamespace(delete=AsyncMock(), message_id=1)
    reply_text = AsyncMock(return_value=status_message)
    reply_photo = AsyncMock(return_value=SimpleNamespace(delete=AsyncMock()))
    message = SimpleNamespace(
        reply_text=reply_text,
        reply_photo=reply_photo,
    )
    user = SimpleNamespace(id=42)
    chat = SimpleNamespace(id=100500)
    return SimpleNamespace(message=message, effective_user=user, effective_chat=chat)


@pytest.fixture
def fake_context() -> Any:
    """Создает минимальный контекст Telegram с AsyncMock ботом."""
    class _App:
        def __init__(self) -> None:
            self.bot_data: dict[str, Any] = {"bot": SimpleNamespace(stop=AsyncMock())}
            self.updater = SimpleNamespace(stop=AsyncMock())

        async def stop(self) -> None:
            return None

    class _Context:
        def __init__(self) -> None:
            self.args: list[str] = []
            self.application = _App()
            self.bot = SimpleNamespace(
                send_document=AsyncMock(),
                send_message=AsyncMock(),
                send_photo=AsyncMock(),
            )

    return _Context()


@pytest.fixture
def async_retry_stub(monkeypatch: Any) -> Callable[[Any], None]:
    """Фикстура, подменяющая _retry_on_connect_error на прямой вызов функции."""

    def _apply(target: Any) -> None:
        async def _direct(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        monkeypatch.setattr(target, "_retry_on_connect_error", _direct)

    return _apply


@pytest.fixture(scope="function", autouse=False)
def reset_singletons() -> Generator[None, None, None]:
    """
    Сбрасывает состояние синглтонов перед тестом для обеспечения изоляции.

    Используйте эту фикстуру в тестах, которые мутируют состояние синглтонов
    (CeleryServices context, DispatchRegistry и др.).

    Пример использования:
        @pytest.mark.asyncio
        async def test_something(reset_singletons):
            # тест использует синглтоны
    """
    import infra.celery.context as celery_context_module

    # Сохраняем исходное состояние
    original_context = celery_context_module._services_context

    # Сбрасываем состояние
    celery_context_module._services_context = None

    try:
        yield
    finally:
        # Восстанавливаем исходное состояние
        celery_context_module._services_context = original_context


@pytest_asyncio.fixture
async def gigachat_client() -> AsyncIterator[Any]:
    """
    Фикстура для создания GigaChatTextClient с автоматическим закрытием сессии.

    Использование:
        @pytest.mark.asyncio
        async def test_something(gigachat_client):
            result = await gigachat_client.generate_text("test")

    Для кастомных параметров создавайте клиент вручную в тесте:
        @pytest.mark.asyncio
        async def test_something():
            client = GigaChatTextClient(auth_url="...", verify_ssl=False)
            try:
                # тест
            finally:
                await client.aclose()
    """
    from shared.config import GigaChatConfig, HttpTimeoutConfig
    from infra.clients.gigachat_text import GigaChatTextClient

    timeout = HttpTimeoutConfig(total=60, connect=10, sock_read=30)
    config = GigaChatConfig(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        models_url="https://example.test/models",
        authorization_key="dummy",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
        prompt_timeout=timeout,
        models_timeout=timeout,
        token_timeout=timeout,
    )
    client = GigaChatTextClient(config=config)
    try:
        yield client
    finally:
        await client.aclose()
