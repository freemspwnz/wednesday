# Руководство по написанию тестов

Этот документ содержит детальные правила написания тестов для проекта Wednesday Frog Bot.

## Содержание

1. [Инструменты и Среда](#инструменты-и-среда)
2. [Мокирование внешних зависимостей](#мокирование-внешних-зависимостей)
3. [Тестирование бизнес-логики (services/)](#тестирование-бизнес-логики-services)
4. [Тестирование обработчиков (bot/)](#тестирование-обработчиков-bot)
5. [Фикстуры (Fixtures)](#фикстуры-fixtures)
6. [Маркеры тестов](#маркеры-тестов)
7. [Правила написания тестов](#правила-написания-тестов)
8. [CI/Pre-commit проверки](#cipre-commit-проверки)

---

## Инструменты и Среда

### Используемые инструменты

Проект использует следующие инструменты для тестирования:

- **`pytest`** (9.0.0) — основной фреймворк для тестирования
- **`pytest-asyncio`** (1.3.0) — поддержка асинхронных тестов
- **`pytest-cov`** (7.0.0) — измерение покрытия кода
- **`pytest-xdist`** (3.6.1) — параллельный запуск тестов
- **`unittest.mock`** — мокирование объектов (встроен в Python)
- **`pytest-mock`** — интеграция pytest с unittest.mock (через `mocker` фикстуру)

### Конфигурация pytest

Настройки pytest находятся в `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "unit: быстрые модульные тесты без внешних зависимостей",
    "integration: интеграционные тесты с Postgres/Redis без Celery e2e",
    "db: тест требует Postgres",
    "redis: тест требует Redis",
    "celery: тест требует Celery worker/beat",
    "e2e: end-to-end сценарии с внешними сервисами",
    "infra: инфраструктурные/диагностические проверки",
    "slow: долгие сценарии, исключаются из быстрых прогонов",
]
asyncio_mode = "strict"
asyncio_default_test_loop_scope = "session"
```

### Запуск тестов

#### Локальный запуск (без Docker)

**Unit-тесты** (быстрые, без внешних зависимостей):
```bash
make test-unit
# или напрямую:
pytest -m "unit" -n auto
```

**Integration-тесты** (требуют запущенных контейнеров):
```bash
# 1. Поднять контейнеры
make test-up

# 2. Запустить тесты
make test-integration
```

**E2E-тесты** (требуют всех контейнеров, включая Celery worker):
```bash
make test-up
make test-e2e
```

#### Запуск через Docker Compose

Все тесты могут быть запущены внутри Docker контейнера:

```bash
# Поднять контейнеры
make test-up

# Запустить тесты в контейнере
docker compose -p wednesday_test -f tests/docker-compose.test.yml \
  --env-file tests/.env.test run --rm tests pytest -m "integration"
```

#### Параллельный запуск

Проект использует `pytest-xdist` для параллельного запуска тестов:

```bash
# Автоматическое определение количества процессов
pytest -n auto

# Явное указание количества процессов
pytest -n 4
```

**Важно:** E2E и Celery тесты обычно не запускаются параллельно из-за конфликтов ресурсов.

### Покрытие кода (pytest-cov)

**Запуск с покрытием:**
```bash
pytest --cov=bot --cov=services --cov=utils \
       --cov-report=term --cov-report=html
```

**Просмотр отчёта:**
```bash
# Терминальный отчёт
pytest --cov=bot --cov=services --cov=utils --cov-report=term

# HTML отчёт
pytest --cov=bot --cov=services --cov=utils --cov-report=html
open htmlcov/index.html
```

**Стандарты покрытия:**
- Проект не устанавливает минимальный порог покрытия (`--cov-fail-under=0`)
- Рекомендуется поддерживать покрытие выше 70% для критичных модулей
- Покрытие измеряется для модулей: `bot`, `services`, `utils`

---

## Мокирование внешних зависимостей

### Базы данных (PostgreSQL)

#### Подход 1: Фикстуры для очистки таблиц

Для integration-тестов используется фикстура `cleanup_tables`, которая очищает все таблицы перед каждым тестом:

```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_chats_store(cleanup_tables):
    """Тест с очисткой таблиц перед запуском."""
    store = ChatsStore()
    await store.add_chat(12345, "Test Chat")
    chat_ids = await store.list_chat_ids()
    assert 12345 in chat_ids
```

**Преимущества:**
- Полная изоляция тестов
- Реальные SQL-запросы проверяются
- Подходит для тестов, проверяющих commit'ы в БД

#### Подход 2: Транзакционный rollback

Для быстрых тестов используется фикстура `postgres_transaction`, которая создаёт транзакцию и откатывает её после теста:

```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_chats_store_fast(postgres_transaction):
    """Быстрый тест с транзакционным rollback."""
    store = ChatsStore()
    await store.add_chat(12345, "Test Chat")
    # Все изменения будут откачены после теста
```

**Преимущества:**
- Быстрее, чем TRUNCATE
- Подходит для тестов без проверки commit'ов

**Ограничения:**
- Не подходит для тестов, проверяющих commit'ы
- Может не работать с некоторыми типами DDL операций

#### Подход 3: In-memory хранилища для unit-тестов

Для unit-тестов используется in-memory реализация `ModelsStore`:

```python
@pytest.mark.unit
def test_models_store():
    """Unit-тест с in-memory хранилищем."""
    # patch_models_store автоматически подменяет ModelsStore
    # на _InMemoryModelsStore для unit-тестов
    from utils.models_store import ModelsStore
    store = ModelsStore()  # Использует in-memory реализацию
```

Фикстура `patch_models_store` автоматически применяется для всех unit-тестов (autouse).

#### Подход 4: Мокирование DAO/ORM слоёв

Для изоляции бизнес-логики можно мокировать методы хранилищ:

```python
@pytest.mark.unit
async def test_service_with_mocked_store(mocker):
    """Тест сервиса с мокированным хранилищем."""
    mock_store = mocker.AsyncMock()
    mock_store.get_chat.return_value = {"id": 12345, "name": "Test"}

    service = MyService(store=mock_store)
    result = await service.get_chat_info(12345)
    assert result["name"] == "Test"
```

### Кэш/Очереди (Redis/Celery)

#### Мокирование Redis для unit-тестов

Для unit-тестов используется in-memory реализация Redis (`_InMemoryRedis`):

```python
from utils.redis_client import _InMemoryRedis

@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiter():
    """Unit-тест rate limiter с in-memory Redis."""
    backend = _InMemoryRedis()
    limiter = RateLimiter(redis_client=backend, prefix="test:", window=60, limit=3)

    assert await limiter.is_allowed("user-1") is True
    assert await limiter.is_allowed("user-1") is True
    assert await limiter.is_allowed("user-1") is True
    assert await limiter.is_allowed("user-1") is False  # Лимит превышен
```

**Преимущества:**
- Не требует запущенного Redis
- Быстрое выполнение
- Полная изоляция тестов

#### Мокирование Celery tasks

Для unit-тестов Celery задач используется `unittest.mock` для подмены задач:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_celery_task_with_mock(mocker):
    """Unit-тест Celery задачи с моками."""
    # Мокируем зависимости
    mock_bot = mocker.AsyncMock()
    mock_bot.send_wednesday_frog = mocker.AsyncMock(return_value={"status": "success"})

    with mocker.patch("services.celery_tasks.CeleryServices.get_bot", return_value=mock_bot):
        # Обходим декораторы Celery для прямого вызова функции
        task_func = send_wednesday_frog_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        result = await task_func(mock_self, slot_time="09:00")
        assert result["status"] == "success"
```

**Важно:** Для тестирования Celery задач необходимо обходить декораторы `@celery_app.task` и `@log_celery_task`, получая исходную функцию через `__wrapped__`.

#### Изоляция Celery очередей для E2E тестов

Для E2E тестов используется фикстура `celery_test_queues`, которая создаёт уникальные очереди:

```python
@pytest.mark.e2e
@pytest.mark.celery
def test_celery_task_e2e(celery_test_queues):
    """E2E тест с изолированными очередями Celery."""
    # celery_test_queues создаёт уникальные очереди для теста
    result = celery_app_test.send_task('test.ping', queue=celery_test_queues.queue_name)
    assert result.get(timeout=5) == "pong"
```

**Преимущества:**
- Изоляция тестов друг от друга
- Параллельный запуск E2E тестов
- Избежание конфликтов в очередях

### Внешние API (Kandinsky/GigaChat)

#### Подход 1: Структурные моки (Protocol-based)

Проект использует Protocol-интерфейсы (`ITextToImageClient`, `ITextToTextClient`) для Dependency Injection. Для тестов созданы мок-реализации:

```python
from tests._doubles.clients import MockTextToImageClient, MockTextToTextClient

@pytest.mark.unit
@pytest.mark.asyncio
async def test_image_generator():
    """Тест генератора с мок-клиентами."""
    image_client = MockTextToImageClient(generate_response=b"fake-image")
    text_client = MockTextToTextClient(generate_response="fake prompt")

    generator = ImageGenerator(
        image_client=image_client,
        text_client=text_client,
    )

    result = await generator.generate_frog_image(user_id=123)
    assert result is not None
    image, caption = result
    assert image == b"fake-image"

    # Проверяем, что клиент был вызван
    assert len(image_client.calls) == 1
    assert image_client.calls[0].prompt is not None
```

**Преимущества:**
- Типобезопасность (mypy проверяет совместимость)
- Детерминированное поведение
- Возможность проверки вызовов через `calls`

#### Подход 2: Мокирование HTTP-сессий

Для тестирования клиентов напрямую можно мокировать HTTP-сессии:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_gigachat_client(monkeypatch):
    """Тест GigaChat клиента с мокированной сессией."""
    client = GigaChatTextClient(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        authorization_key="dummy",
    )

    # Создаём мок-сессию
    class DummySession:
        async def post(self, *args, **kwargs):
            class Response:
                async def json(self):
                    return {"access_token": "dummy-token", "expires_in": 1800}
            return Response()

    dummy_session = DummySession()
    monkeypatch.setattr(client, "_session", dummy_session)

    token = await client._get_access_token()
    assert token == "dummy-token"
```

#### Подход 3: Мокирование через pytest-mock

Для более сложных сценариев используется `pytest-mock`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_with_http_mock(mocker):
    """Тест сервиса с мокированным HTTP-клиентом."""
    # Мокируем aiohttp.ClientSession
    mock_session = mocker.AsyncMock()
    mock_response = mocker.AsyncMock()
    mock_response.json = mocker.AsyncMock(return_value={"result": "ok"})
    mock_session.post = mocker.AsyncMock(return_value=mock_response)

    with mocker.patch("aiohttp.ClientSession", return_value=mock_session):
        service = MyService()
        result = await service.call_api()
        assert result == {"result": "ok"}
```

#### Подход 4: Мокирование конкретных методов клиента

Для частичного мокирования можно патчить отдельные методы:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_generator_with_partial_mock(monkeypatch):
    """Тест генератора с частично мокированным клиентом."""
    from services.clients.kandinsky import KandinskyClient

    generator = ImageGenerator()
    kandinsky_client = KandinskyClient()

    # Мокируем только метод check_api_status
    monkeypatch.setattr(
        kandinsky_client,
        "check_api_status",
        AsyncMock(return_value=(True, "✅ API доступен", ["Model-1"], (None, None))),
    )
    generator._kandinsky_client = kandinsky_client

    ok, message, models, current = await generator.check_api_status()
    assert ok is True
```

**Рекомендации:**
- Предпочитайте структурные моки (`MockTextToImageClient`) для unit-тестов
- Используйте Dependency Injection для подмены клиентов
- Для integration-тестов можно использовать реальные клиенты с мокированными HTTP-сессиями

---

## Тестирование бизнес-логики (services/)

### Dependency Injection для подмены зависимостей

Сервисы в проекте используют Dependency Injection через конструкторы, что упрощает тестирование:

```python
# services/image_generator.py
class ImageGenerator:
    def __init__(
        self,
        image_client: ITextToImageClient | None = None,
        text_client: ITextToTextClient | None = None,
    ):
        # Принимает абстрактные интерфейсы
        if image_client is None:
            self._image_client = create_image_client()
        else:
            self._image_client = image_client
```

**Пример теста с DI:**
```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_image_generator_with_di():
    """Тест генератора с подменёнными зависимостями."""
    # Создаём мок-клиенты
    image_client = MockTextToImageClient(generate_response=b"test-image")
    text_client = MockTextToTextClient(generate_response="test prompt")

    # Передаём их в конструктор
    generator = ImageGenerator(
        image_client=image_client,
        text_client=text_client,
    )

    # Тестируем бизнес-логику
    result = await generator.generate_frog_image(user_id=123)
    assert result is not None
```

### Тестирование сервисов с внешними зависимостями

#### Пример: Тестирование PromptGenerator

```python
@pytest.mark.unit
def test_prompt_storage(tmp_path, monkeypatch):
    """Тест хранилища промптов."""
    # Мокируем логгер
    fake_logger = MagicMock()
    monkeypatch.setattr("services.prompt_generator.get_logger", lambda *args, **kwargs: fake_logger)

    storage = PromptStorage(base_dir=tmp_path)
    path_str = storage.save_prompt("A frog", source="test")

    assert path_str is not None
    file_path = Path(path_str)
    assert file_path.is_file()
    assert file_path.read_text(encoding="utf-8") == "A frog"
```

#### Пример: Тестирование RateLimiter

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiter():
    """Тест rate limiter с in-memory Redis."""
    backend = _InMemoryRedis()
    limiter = RateLimiter(redis_client=backend, prefix="test:", window=60, limit=3)

    key = "user-1"
    assert await limiter.is_allowed(key) is True
    assert await limiter.is_allowed(key) is True
    assert await limiter.is_allowed(key) is True
    assert await limiter.is_allowed(key) is False  # Лимит превышен
```

### Тестирование асинхронных сервисов

Все асинхронные тесты должны использовать `@pytest.mark.asyncio`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_service():
    """Тест асинхронного сервиса."""
    service = MyAsyncService()
    result = await service.do_something()
    assert result == "expected"
```

### Тестирование сервисов с интеграцией БД

Для тестов, которые проверяют взаимодействие с БД, используйте integration-тесты:

```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_image_generator_with_db_cache(cleanup_tables, monkeypatch):
    """Тест генератора с кешированием в БД."""
    image_client = MockTextToImageClient(generate_response=b"cached-image")
    text_client = MockTextToTextClient(generate_response="cached prompt")

    generator = ImageGenerator(
        image_client=image_client,
        text_client=text_client,
    )

    # Первый вызов — создаёт запись в БД
    result1 = await generator.generate_frog_image(user_id=123)
    assert result1 is not None

    # Второй вызов — использует кеш из БД
    result2 = await generator.generate_frog_image(user_id=123)
    assert result2 is not None

    # Генерация должна была произойти только один раз
    assert len(image_client.calls) == 1
```

---

## Тестирование обработчиков (bot/)

### Симуляция событий Telegram

Для тестирования обработчиков используются фикстуры `fake_update` и `fake_context`:

```python
@pytest.mark.asyncio
async def test_start_command(fake_update, fake_context, async_retry_stub):
    """Тест команды /start."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    await handler.start_command(fake_update, fake_context)

    # Проверяем, что было отправлено сообщение
    fake_update.message.reply_text.assert_awaited()
```

#### Структура fake_update

Фикстура `fake_update` создаёт объект, имитирующий `telegram.Update`:

```python
@pytest.fixture
def fake_update():
    """Создает простую структуру Update с асинхронным reply_text."""
    status_message = SimpleNamespace(delete=AsyncMock())
    reply_text = AsyncMock(return_value=status_message)
    message = SimpleNamespace(reply_text=reply_text)
    user = SimpleNamespace(id=42)
    chat = SimpleNamespace(id=100500)
    return SimpleNamespace(message=message, effective_user=user, effective_chat=chat)
```

#### Структура fake_context

Фикстура `fake_context` создаёт объект, имитирующий `telegram.ext.ContextTypes.DEFAULT_TYPE`:

```python
@pytest.fixture
def fake_context():
    """Создает минимальный контекст Telegram с AsyncMock ботом."""
    class _Context:
        def __init__(self):
            self.args = []
            self.application = _App()
            self.bot = SimpleNamespace(
                send_document=AsyncMock(),
                send_message=AsyncMock(),
                send_photo=AsyncMock(),
            )
    return _Context()
```

### Тестирование команд с аргументами

```python
@pytest.mark.asyncio
async def test_set_frog_limit_command(fake_update, fake_context):
    """Тест команды /set_frog_limit с аргументами."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    # Настраиваем админ-права
    class AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True
    handler.admins_store = AdminOk()

    # Устанавливаем аргументы команды
    fake_context.args = ["80"]
    fake_context.application.bot_data["usage"] = FakeUsage()

    await handler.set_frog_limit_command(fake_update, fake_context)

    # Проверяем ответ
    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Порог /frog установлен" in message
```

### Тестирование FSM-переходов

Для тестирования FSM (Finite State Machine) можно мокировать состояние пользователя:

```python
@pytest.mark.asyncio
async def test_fsm_transition(fake_update, fake_context):
    """Тест FSM-перехода."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    # Устанавливаем начальное состояние
    fake_context.user_data["state"] = "waiting_for_input"

    await handler.handle_input(fake_update, fake_context)

    # Проверяем, что состояние изменилось
    assert fake_context.user_data["state"] == "processing"
```

### Тестирование обработчиков с реальными хранилищами

Для integration-тестов обработчиков можно использовать реальные хранилища:

```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_status_command_with_postgres(fake_update, fake_context, cleanup_tables):
    """Integration-тест команды /status с реальной БД."""
    from utils.chats_store import ChatsStore
    from utils.metrics import Metrics
    from utils.usage_tracker import UsageTracker

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    # Используем реальные хранилища
    usage = UsageTracker(storage_path="ignored.json")
    chats = ChatsStore(storage_path="ignored.json")
    metrics = Metrics(storage_path="ignored.json")

    fake_context.application.bot_data["usage"] = usage
    fake_context.application.bot_data["chats"] = chats
    fake_context.application.bot_data["metrics"] = metrics

    await handler.status_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Статус бота" in text
```

### Мокирование retry-механизмов

Для упрощения тестов обработчиков используется фикстура `async_retry_stub`:

```python
@pytest.mark.asyncio
async def test_handler_with_retry_stub(fake_update, fake_context, async_retry_stub):
    """Тест обработчика с отключённым retry."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)  # Отключает retry для теста

    await handler.start_command(fake_update, fake_context)
    # Тест выполняется без задержек retry
```

---

## Фикстуры (Fixtures)

### Autouse фикстуры

Эти фикстуры применяются автоматически ко всем тестам:

#### `session_env_defaults`

Устанавливает переменные окружения на всю сессию тестов:

```python
@pytest.fixture(scope="session", autouse=True)
def session_env_defaults():
    """Устанавливает обязательные переменные окружения до импорта модулей."""
    # Устанавливает TELEGRAM_BOT_TOKEN, POSTGRES_*, REDIS_* и др.
    yield
    # Восстанавливает переменные после всех тестов
```

**Использование:** Применяется автоматически, не нужно указывать в параметрах теста.

#### `base_env`

Устанавливает переменные окружения для каждого теста:

```python
@pytest.fixture(autouse=True)
def base_env(monkeypatch, tmp_path_factory):
    """Гарантирует наличие обязательных переменных окружения."""
    env_defaults = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "KANDINSKY_API_KEY": "test-api",
        # ...
    }
    for key, value in env_defaults.items():
        monkeypatch.setenv(key, value)
```

**Использование:** Применяется автоматически.

#### `patch_models_store`

Подменяет `ModelsStore` на in-memory реализацию для unit-тестов:

```python
@pytest.fixture(autouse=True)
def patch_models_store(monkeypatch, request):
    """Подменяет ModelsStore на простую in-memory реализацию."""
    # Исключает тесты из test_utils/test_models_store.py
    # и интеграционные тесты с маркерами db/integration/e2e
    if not should_skip_patch:
        monkeypatch.setattr(models_store_module, "ModelsStore", _InMemoryModelsStore)
```

**Использование:** Применяется автоматически для unit-тестов, отключается для integration/e2e тестов.

### Opt-in фикстуры

Эти фикстуры нужно явно указывать в параметрах теста:

#### `cleanup_tables`

Очищает все таблицы PostgreSQL перед тестом:

```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_with_db(cleanup_tables):
    """Тест с очисткой таблиц."""
    # Все таблицы очищены перед тестом
    store = ChatsStore()
    await store.add_chat(12345, "Test")
```

**Использование:** Требует маркер `@pytest.mark.db`.

#### `postgres_transaction`

Использует транзакционный rollback для изоляции:

```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_with_transaction(postgres_transaction):
    """Быстрый тест с транзакционным rollback."""
    # Все изменения будут откачены после теста
    store = ChatsStore()
    await store.add_chat(12345, "Test")
```

**Использование:** Требует маркер `@pytest.mark.db`. Быстрее, чем `cleanup_tables`, но не подходит для тестов с commit'ами.

#### `async_postgres_pool`

Session-фикстура для создания пула соединений PostgreSQL:

```python
@pytest_asyncio.fixture(scope="session")
async def async_postgres_pool():
    """Session-фикстура для создания пула соединений PostgreSQL."""
    pool = await init_postgres_pool(min_size=1, max_size=2)
    yield pool
    await close_postgres_pool()
```

**Использование:** Используется внутренне другими фикстурами, обычно не нужно указывать явно.

#### `celery_test_queues`

Создаёт уникальные очереди Celery для изоляции E2E тестов:

```python
@pytest.mark.e2e
@pytest.mark.celery
def test_celery_task(celery_test_queues):
    """E2E тест с изолированными очередями."""
    result = celery_app_test.send_task('test.ping', queue=celery_test_queues.queue_name)
    assert result.get(timeout=5) == "pong"
```

**Использование:** Требует маркеры `@pytest.mark.e2e` и `@pytest.mark.celery`.

#### `celery_worker_ready`

Ожидает готовности Celery worker перед запуском E2E тестов:

```python
@pytest.mark.e2e
@pytest.mark.celery
def test_celery_e2e(celery_worker_ready):
    """E2E тест с проверкой готовности worker."""
    # Worker готов к выполнению задач
    result = celery_app_test.send_task('test.ping')
    assert result.get(timeout=5) == "pong"
```

**Использование:** Требует маркеры `@pytest.mark.e2e` и `@pytest.mark.celery`.

#### `reset_singletons`

Сбрасывает состояние синглтонов перед тестом:

```python
@pytest.mark.asyncio
async def test_with_singleton_reset(reset_singletons):
    """Тест с сбросом синглтонов."""
    # Состояние CeleryServices сброшено
    await CeleryServices.get_bot()
```

**Использование:** Используйте для тестов, которые мутируют состояние синглтонов.

#### `fake_update` и `fake_context`

Создают моки для событий Telegram:

```python
@pytest.mark.asyncio
async def test_handler(fake_update, fake_context):
    """Тест обработчика с моками Telegram."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    await handler.start_command(fake_update, fake_context)
    fake_update.message.reply_text.assert_awaited()
```

**Использование:** Для всех тестов обработчиков бота.

#### `async_retry_stub`

Отключает retry-механизм для упрощения тестов:

```python
@pytest.mark.asyncio
async def test_handler(fake_update, fake_context, async_retry_stub):
    """Тест обработчика без retry."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)  # Отключает retry
    await handler.start_command(fake_update, fake_context)
```

**Использование:** Для тестов обработчиков, где retry не нужен.

#### `gigachat_client`

Создаёт GigaChat клиент с автоматическим закрытием:

```python
@pytest.mark.asyncio
async def test_gigachat(gigachat_client):
    """Тест с GigaChat клиентом."""
    result = await gigachat_client.generate_text("test")
    # Клиент автоматически закроется после теста
```

**Использование:** Для тестов, требующих реального GigaChat клиента.

#### `reload_config`

Возвращает функцию для перезагрузки конфигурации:

```python
def test_config_reload(reload_config):
    """Тест с перезагрузкой конфигурации."""
    config_module = reload_config()
    # Конфигурация перезагружена с актуальными env
```

**Использование:** Для тестов, проверяющих загрузку конфигурации.

---

## Маркеры тестов

### Основные маркеры типов тестов

#### `@pytest.mark.unit` — Unit-тесты

**Когда использовать:**
- Быстрые тесты без внешних зависимостей (БД, Redis, Celery)
- Тесты с моками всех внешних сервисов
- Тесты изоляции отдельных функций/классов
- Не требуют контейнеров

**Характеристики:**
- Выполняются быстро (< 1 секунды каждый)
- Не требуют внешних сервисов
- Используют моки для всех зависимостей
- Могут запускаться параллельно без ограничений

**Примеры правильного использования:**
```python
@pytest.mark.unit
def test_calculate_sum():
    """Быстрый unit-тест без зависимостей."""
    assert calculate_sum(2, 3) == 5

@pytest.mark.unit
def test_format_message(mocker):
    """Unit-тест с моками."""
    mock_client = mocker.patch('services.clients.gigachat.GigaChatClient')
    # тест с моками
```

**Антипаттерны:**
```python
# ❌ НЕПРАВИЛЬНО: unit-тест с реальной БД
@pytest.mark.unit
async def test_store(cleanup_tables):
    # использует реальную БД — должен быть @pytest.mark.integration + @pytest.mark.db

# ❌ НЕПРАВИЛЬНО: unit-тест с Redis
@pytest.mark.unit
def test_cache(redis_client):
    # использует Redis — должен быть @pytest.mark.integration + @pytest.mark.redis
```

#### `@pytest.mark.integration` — Integration-тесты

**Когда использовать:**
- Тесты с реальными Postgres/Redis, но без Celery e2e
- Тесты взаимодействия нескольких компонентов
- Требуют контейнеров Postgres/Redis

**Характеристики:**
- Выполняются медленнее unit-тестов (1-5 секунд каждый)
- Требуют запущенных контейнеров Postgres/Redis
- Проверяют взаимодействие компонентов
- Могут запускаться параллельно с xdist

**Примеры правильного использования:**
```python
@pytest.mark.integration
@pytest.mark.db
async def test_chats_store(cleanup_tables):
    """Integration-тест с БД."""
    store = ChatsStore()
    await store.add_chat(12345)
    chat_ids = await store.list_chat_ids()
    assert 12345 in chat_ids

@pytest.mark.integration
@pytest.mark.redis
def test_rate_limiter():
    """Integration-тест с Redis."""
    limiter = RateLimiter()
    # тест с Redis
```

**Антипаттерны:**
```python
# ❌ НЕПРАВИЛЬНО: integration без маркера db/redis
@pytest.mark.integration
async def test_store(cleanup_tables):
    # использует БД, но нет @pytest.mark.db

# ❌ НЕПРАВИЛЬНО: integration с Celery e2e
@pytest.mark.integration
def test_celery_task(celery_worker_ready):
    # Celery e2e должен быть @pytest.mark.e2e + @pytest.mark.celery
```

#### `@pytest.mark.e2e` — End-to-End тесты

**Когда использовать:**
- Полные end-to-end сценарии с реальными сервисами
- Тесты с Celery worker (реальные задачи)
- Требуют всех контейнеров (Postgres, Redis, Celery Worker)

**Характеристики:**
- Выполняются медленно (5-30 секунд каждый)
- Требуют всех запущенных контейнеров
- Проверяют полные сценарии работы системы
- Обычно не запускаются параллельно

**Примеры правильного использования:**
```python
@pytest.mark.e2e
@pytest.mark.celery
async def test_celery_task_execution(celery_worker_ready):
    """E2E тест выполнения Celery задачи."""
    result = celery_app_test.send_task('test.ping')
    assert result.get(timeout=5) == "pong"
```

#### `@pytest.mark.infra` — Инфраструктурные тесты

**Когда использовать:**
- Диагностические/инфраструктурные проверки
- Тесты доступности сервисов, health checks
- Обычно комбинируется с `e2e`

**Характеристики:**
- Проверяют инфраструктуру, а не бизнес-логику
- Могут запускаться реже, чем основные тесты
- Обычно комбинируются с `e2e` и `celery`

**Примеры правильного использования:**
```python
@pytest.mark.e2e
@pytest.mark.infra
@pytest.mark.celery
def test_celery_worker_availability(celery_worker_ready):
    """Инфраструктурный тест доступности Celery worker."""
    # проверка доступности worker
```

### Ресурсные маркеры

#### `@pytest.mark.db` — Тесты с PostgreSQL

**Когда использовать:**
- Тесты, использующие фикстуру `cleanup_tables` или `postgres_transaction`
- Тесты, работающие с хранилищами (ChatsStore, AdminsStore и т.д.)

**Обязателен для:**
- Тестов, использующих `cleanup_tables`
- Тестов, использующих `postgres_transaction`
- Тестов, работающих с любыми store-классами

**Пример:**
```python
@pytest.mark.integration
@pytest.mark.db
async def test_chats_store(cleanup_tables):
    # тест с БД
```

#### `@pytest.mark.redis` — Тесты с Redis

**Когда использовать:**
- Тесты, использующие Redis (кэш, rate limiter и т.д.)

**Обязателен для:**
- Тестов, использующих Redis клиент
- Тестов, работающих с rate limiter
- Тестов, использующих кэш

**Пример:**
```python
@pytest.mark.integration
@pytest.mark.redis
def test_rate_limiter():
    # тест с Redis
```

#### `@pytest.mark.celery` — Тесты с Celery

**Когда использовать:**
- Тесты, использующие фикстуру `celery_test_queues` или `celery_worker_ready`
- Тесты, отправляющие задачи в Celery

**Обязателен для:**
- Тестов, использующих `celery_test_queues`
- Тестов, использующих `celery_worker_ready`
- Тестов, отправляющих задачи в Celery

**Пример:**
```python
@pytest.mark.e2e
@pytest.mark.celery
def test_celery_task(celery_worker_ready):
    # тест с Celery
```

#### `@pytest.mark.slow` — Долгие тесты

**Когда использовать:**
- Тесты, которые выполняются дольше обычного (>5 секунд)
- Тесты с большими таймаутами
- Тесты, которые можно запускать реже

**Пример:**
```python
@pytest.mark.e2e
@pytest.mark.slow
def test_long_running_task():
    # долгий тест
```

### Комбинации маркеров

**Правильные комбинации:**
```python
# Unit-тест (только unit)
@pytest.mark.unit
def test_unit():
    pass

# Integration с БД
@pytest.mark.integration
@pytest.mark.db
async def test_with_db(cleanup_tables):
    pass

# Integration с Redis
@pytest.mark.integration
@pytest.mark.redis
def test_with_redis():
    pass

# E2E с Celery
@pytest.mark.e2e
@pytest.mark.celery
def test_celery_e2e(celery_worker_ready):
    pass

# E2E инфраструктурный
@pytest.mark.e2e
@pytest.mark.infra
@pytest.mark.celery
def test_infra(celery_worker_ready):
    pass
```

**Неправильные комбинации (антипаттерны):**
```python
# ❌ unit + db (unit не должен использовать БД)
@pytest.mark.unit
@pytest.mark.db
async def test_unit_with_db(cleanup_tables):
    pass

# ❌ integration без db/redis (если использует ресурсы)
@pytest.mark.integration
async def test_with_db(cleanup_tables):  # нет @pytest.mark.db
    pass

# ❌ e2e без celery (если использует Celery)
@pytest.mark.e2e
def test_celery(celery_worker_ready):  # нет @pytest.mark.celery
    pass
```

---

## Фикстуры: autouse vs opt-in

### Правила создания autouse фикстур

**Autouse фикстуры должны использоваться только для:**
- Базовых настроек окружения (переменные окружения, моки хранилищ)
- Настроек, которые нужны всем тестам
- Настроек, которые не влияют на производительность

**Разрешённые autouse фикстуры:**
1. `session_env_defaults` — устанавливает переменные окружения на сессию
2. `base_env` — устанавливает переменные окружения для каждого теста
3. `patch_models_store` — подменяет ModelsStore на in-memory реализацию

**Правило:** Новые autouse фикстуры можно добавлять только с обоснованием и после обсуждения с командой.

### Правила создания opt-in фикстур

**Opt-in фикстуры должны использоваться для:**
- Ресурсных зависимостей (БД, Redis, Celery)
- Фикстур, которые требуют времени на инициализацию
- Фикстур, которые нужны не всем тестам

**Примеры opt-in фикстур:**
1. `cleanup_tables` — очистка таблиц PostgreSQL
2. `postgres_transaction` — транзакционный rollback
3. `celery_test_queues` — изолированные очереди Celery
4. `reset_singletons` — сброс состояния синглтонов

### Когда использовать autouse, когда opt-in

**Используйте autouse для:**
- Базовых настроек окружения (переменные окружения, моки хранилищ)
- Настроек, которые нужны всем тестам
- Настроек, которые не влияют на производительность

**Используйте opt-in для:**
- Ресурсных зависимостей (БД, Redis, Celery)
- Фикстур, которые требуют времени на инициализацию
- Фикстур, которые нужны не всем тестам

**Примеры правильного использования:**

```python
# ✅ ПРАВИЛЬНО: autouse фикстуры применяются автоматически
@pytest.mark.unit
def test_something():
    # session_env_defaults, base_env, patch_models_store применены автоматически
    pass

# ✅ ПРАВИЛЬНО: opt-in фикстура для БД
@pytest.mark.integration
@pytest.mark.db
async def test_with_db(cleanup_tables):
    # cleanup_tables нужно указать явно
    pass

# ❌ НЕПРАВИЛЬНО: не нужно указывать autouse фикстуры
@pytest.mark.unit
def test_something(session_env_defaults, base_env, patch_models_store):
    # эти фикстуры применяются автоматически
    pass
```

---

## Правила написания тестов

### Unit-тесты

**Структура:**
- Быстрые тесты без внешних зависимостей
- Используют моки для всех зависимостей
- Проверяют изоляцию отдельных функций/классов

**Пример:**
```python
@pytest.mark.unit
def test_format_message(mocker):
    """Unit-тест форматирования сообщения."""
    # Мокируем внешние зависимости
    mock_client = mocker.patch('services.clients.gigachat.GigaChatClient')
    mock_client.return_value.generate.return_value = "Test response"

    # Тестируем функцию
    result = format_message("test")
    assert result == "Test response"
```

**Правила:**
- Не использовать реальные БД/Redis/Celery
- Использовать моки для всех внешних зависимостей
- Тесты должны выполняться быстро (< 1 секунды)
- Не требовать контейнеров

### Integration-тесты

**Структура:**
- Тесты с реальными Postgres/Redis, но без Celery e2e
- Проверяют взаимодействие нескольких компонентов
- Используют фикстуры для очистки данных

**Пример:**
```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_chats_store(cleanup_tables):
    """Integration-тест работы с хранилищем чатов."""
    store = ChatsStore()

    # Добавляем чат
    await store.add_chat(12345, "Test Chat")

    # Проверяем, что чат добавлен
    chat_ids = await store.list_chat_ids()
    assert 12345 in chat_ids

    # Удаляем чат
    await store.remove_chat(12345)

    # Проверяем, что чат удалён
    chat_ids = await store.list_chat_ids()
    assert 12345 not in chat_ids
```

**Правила:**
- Использовать реальные БД/Redis (через контейнеры)
- Использовать фикстуры для очистки данных (`cleanup_tables` или `postgres_transaction`)
- Обязательно указывать маркеры `db` или `redis`
- Тесты должны быть изолированы друг от друга

### E2E-тесты

**Структура:**
- Полные end-to-end сценарии с реальными сервисами
- Требуют всех контейнеров (Postgres, Redis, Celery Worker)
- Проверяют полные сценарии работы системы

**Пример:**
```python
@pytest.mark.e2e
@pytest.mark.celery
def test_celery_task_execution(celery_worker_ready):
    """E2E тест выполнения Celery задачи."""
    # Отправляем задачу
    result = celery_app_test.send_task('test.ping')

    # Ожидаем результат
    assert result.get(timeout=5) == "pong"
```

**Правила:**
- Требуют всех запущенных контейнеров
- Использовать фикстуру `celery_worker_ready` для проверки готовности worker
- Использовать сниженные таймауты (5-7 секунд)
- Тесты могут выполняться медленно (5-30 секунд)

### Общие правила

**Именование:**
- Имена тестов должны быть описательными
- Использовать формат: `test_<что_тестируется>_<ожидаемое_поведение>`
- Примеры: `test_chats_store_add_chat`, `test_rate_limiter_exceeds_limit`

**Структура:**
- Arrange-Act-Assert (AAA) паттерн
- Чёткое разделение на этапы
- Минимум логики в тестах

**Документация:**
- Добавлять docstrings к тестам
- Объяснять, что тестируется и почему
- Указывать особые условия выполнения

**Пример правильного теста:**
```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_chats_store_add_chat(cleanup_tables):
    """
    Тест добавления чата в хранилище.

    Проверяет, что:
    - Чат успешно добавляется в БД
    - Чат появляется в списке чатов
    """
    # Arrange
    store = ChatsStore()
    chat_id = 12345
    chat_name = "Test Chat"

    # Act
    await store.add_chat(chat_id, chat_name)

    # Assert
    chat_ids = await store.list_chat_ids()
    assert chat_id in chat_ids
```

---

## CI/Pre-commit проверки

### Автоматические проверки

В проекте настроены автоматические проверки качества тестов:

1. **Проверка autouse фикстур**
   - Запрещает добавление новых autouse фикстур без обоснования
   - Разрешены только базовые фикстуры: `session_env_defaults`, `base_env`, `patch_models_store`
   - Выдаёт предупреждение при обнаружении новых autouse фикстур

2. **Проверка маркеров ресурсов**
   - Проверяет, что тесты с `cleanup_tables` имеют маркер `db`
   - Проверяет, что тесты с `celery_test_queues` имеют маркер `celery`
   - Проверяет, что тесты с долгими операциями имеют маркер `slow`
   - Выдаёт предупреждения при отсутствии маркеров

### Как исправить ошибки проверок

#### Ошибка: "Новая autouse фикстура обнаружена"

**Проблема:**
```python
@pytest.fixture(autouse=True)
def new_autouse_fixture():
    # новая autouse фикстура
    pass
```

**Решение:**
1. Если фикстура действительно нужна всем тестам, обсудите с командой
2. Если фикстура нужна не всем тестам, сделайте её opt-in:
```python
@pytest.fixture(autouse=False)  # или просто @pytest.fixture
def new_fixture():
    # opt-in фикстура
    pass
```

#### Ошибка: "Тест использует cleanup_tables, но не имеет маркера db"

**Проблема:**
```python
@pytest.mark.integration
async def test_something(cleanup_tables):  # нет @pytest.mark.db
    pass
```

**Решение:**
Добавьте маркер `db`:
```python
@pytest.mark.integration
@pytest.mark.db
async def test_something(cleanup_tables):
    pass
```

#### Ошибка: "Тест использует celery_test_queues, но не имеет маркера celery"

**Проблема:**
```python
@pytest.mark.e2e
def test_celery(celery_test_queues):  # нет @pytest.mark.celery
    pass
```

**Решение:**
Добавьте маркер `celery`:
```python
@pytest.mark.e2e
@pytest.mark.celery
def test_celery(celery_test_queues):
    pass
```

### Запуск проверок локально

**Через pre-commit:**
```bash
pre-commit run --all-files
```

**Вручную:**
```bash
python tests/check_test_quality.py
```

### Примеры правильного и неправильного кода

**Правильный код:**
```python
# ✅ ПРАВИЛЬНО: unit-тест без зависимостей
@pytest.mark.unit
def test_calculate():
    assert calculate(2, 3) == 5

# ✅ ПРАВИЛЬНО: integration с маркерами
@pytest.mark.integration
@pytest.mark.db
async def test_store(cleanup_tables):
    pass

# ✅ ПРАВИЛЬНО: e2e с celery
@pytest.mark.e2e
@pytest.mark.celery
def test_celery(celery_worker_ready):
    pass
```

**Неправильный код:**
```python
# ❌ НЕПРАВИЛЬНО: unit с БД
@pytest.mark.unit
@pytest.mark.db
async def test_store(cleanup_tables):
    pass

# ❌ НЕПРАВИЛЬНО: integration без маркера db
@pytest.mark.integration
async def test_store(cleanup_tables):
    pass

# ❌ НЕПРАВИЛЬНО: e2e без celery
@pytest.mark.e2e
def test_celery(celery_worker_ready):
    pass
```

---

## Дополнительные ресурсы

- [tests/README.md](../tests/README.md) — краткое руководство по тестам
- [pytest документация](https://docs.pytest.org/) — официальная документация pytest
- [pytest-asyncio документация](https://pytest-asyncio.readthedocs.io/) — документация по async тестам
