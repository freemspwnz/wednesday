# Тесты проекта

## Быстрый старт (матрица маркеров)

- unit: без внешних зависимостей, без БД/Redis/Celery, без slow.
- integration: с Postgres/Redis, но без Celery e2e/infra.
- e2e: end-to-end сценарии; infra — диагностические Celery e2e.
- db/redis/celery: ресурсные зависимости; slow — долгие кейсы.

## Команды

### `make test-unit-no-container`

Запускает unit-тесты без контейнеров (только моки).

**Что запускается:**
- Все тесты с маркером `unit` или без маркеров `integration`, `e2e`, `infra`, `celery`, `db`, `redis`, `slow`
- Быстрые тесты без внешних зависимостей

**Пример вывода:**
```bash
=== Запуск unit без контейнеров (no containers) ===
========================= test session starts ==========================
collected 45 items

tests/test_services/test_prompt_generator.py::test_generate_prompt ... PASSED
tests/test_utils/test_metrics.py::test_record_metric ... PASSED
...

========================= 45 passed in 2.34s ==========================
```

**Ожидаемый результат:**
- Все тесты проходят быстро (< 5 секунд)
- Нет подключений к БД/Redis/Celery
- Создаётся `junit.xml` с результатами

### `make test-integration-containers`

Запускает integration-тесты с контейнерами Postgres/Redis.

**Что запускается:**
- Тесты с маркерами `integration`, `db`, `redis` (без `celery`, `e2e`, `infra`, `slow`)
- Требует запущенных контейнеров Postgres и Redis

**Пример вывода:**
```bash
=== Запуск integration с контейнерами (Postgres/Redis) ===
=== Поднятие тестовых контейнеров ===
...
=== Запуск тестов ===
========================= test session starts ==========================
collected 32 items

tests/test_utils/test_chats_store.py::test_chats_store_add_chat ... PASSED
tests/test_utils/test_metrics.py::test_metrics_with_db ... PASSED
...

---------- coverage: platform linux, python 3.11 -----------
Name                                    Stmts   Miss  Cover
-----------------------------------------------------------
bot/handlers.py                           120     45    62%
services/prompt_generator.py               85     30    65%
...
-----------------------------------------------------------
TOTAL                                     450    225    50%

========================= 32 passed in 15.23s ==========================
```

**Ожидаемый результат:**
- Все тесты проходят
- Coverage ≥ 50% (иначе тесты завершаются с ошибкой)
- Создаётся `coverage.xml` и `junit.xml`

### `make test-integration-containers-xdist`

Запускает integration-тесты параллельно с помощью pytest-xdist.

**Что запускается:**
- Те же тесты, что и `test-integration-containers`
- Параллельный запуск на всех доступных CPU ядрах (`-n auto`)

**Пример вывода:**
```bash
=== Запуск integration с контейнерами (Postgres/Redis) с xdist ===
========================= test session starts ==========================
plugins: xdist-3.5.0
gw0 [32] / gw1 [32] / gw2 [32] / gw3 [32]
...

[gw0] PASSED tests/test_utils/test_chats_store.py::test_chats_store_add_chat
[gw1] PASSED tests/test_utils/test_metrics.py::test_metrics_with_db
...

========================= 32 passed in 8.45s ==========================
```

**Ожидаемый результат:**
- Тесты выполняются быстрее (в 2-4 раза)
- Coverage ≥ 50%
- Создаётся `coverage.xml` и `junit.xml`

**Примечание:** xdist может выявить проблемы с изоляцией тестов. Если тесты падают с xdist, проверьте использование глобальных состояний.

### `make test-e2e`

Запускает E2E тесты без infra-набора.

**Что запускается:**
- Тесты с маркером `e2e` без `infra`
- Требует запущенных контейнеров (Postgres, Redis, Celery Worker)

**Пример вывода:**
```bash
=== Запуск E2E (без infra) ===
=== Поднятие тестовых контейнеров ===
...
=== Запуск тестов ===
========================= test session starts ==========================
collected 8 items

tests/e2e/celery/test_celery_e2e_basic.py::test_celery_ping ... PASSED
tests/e2e/celery/test_celery_e2e_basic.py::test_celery_result_backend ... PASSED
...

========================= 8 passed in 12.34s ==========================
```

**Ожидаемый результат:**
- Все E2E тесты проходят
- Создаётся `junit-e2e.xml`

### `make test-e2e-infra`

Запускает инфраструктурные E2E тесты Celery.

**Что запускается:**
- Тесты с маркерами `e2e` и `infra`
- Диагностические/инфраструктурные проверки

**Пример вывода:**
```bash
=== Запуск Celery infra E2E ===
=== Поднятие тестовых контейнеров ===
...
=== Запуск тестов ===
========================= test session starts ==========================
collected 12 items

tests/test_services/test_celery_e2e.py::test_celery_worker_availability ... PASSED
tests/test_services/test_celery_e2e.py::test_celery_queue_isolation ... PASSED
...

========================= 12 passed in 18.56s ==========================
```

**Ожидаемый результат:**
- Все infra-тесты проходят
- Создаётся `junit-e2e-infra.xml`

## Правила использования маркеров

### Основные маркеры типов тестов

#### `@pytest.mark.unit` — Unit-тесты

**Когда использовать:**
- Быстрые тесты без внешних зависимостей (БД, Redis, Celery)
- Тесты с моками всех внешних сервисов
- Тесты изоляции отдельных функций/классов
- Не требуют контейнеров

**Примеры правильной маркировки:**
```python
@pytest.mark.unit
def test_calculate_sum():
    """Быстрый unit-тест без зависимостей."""
    assert calculate_sum(2, 3) == 5

@pytest.mark.unit
def test_format_message(mocker):
    """Unit-тест с моками."""
    mock_client = mocker.patch('services.clients.gigachat.GigaChatClient')
    # тест
```

**Примеры неправильной маркировки (антипаттерны):**
```python
# ❌ НЕПРАВИЛЬНО: unit-тест с реальной БД
@pytest.mark.unit
async def test_store(cleanup_tables):
    # использует реальную БД — должен быть @pytest.mark.integration

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

**Примеры правильной маркировки:**
```python
@pytest.mark.integration
@pytest.mark.db
async def test_chats_store(cleanup_tables):
    """Integration-тест с БД."""
    store = ChatsStore()
    await store.add_chat(12345)

@pytest.mark.integration
@pytest.mark.redis
def test_rate_limiter(redis_client):
    """Integration-тест с Redis."""
    limiter = RateLimiter()
    # тест
```

**Примеры неправильной маркировки (антипаттерны):**
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

**Примеры правильной маркировки:**
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

**Примеры правильной маркировки:**
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

## Фикстуры: autouse vs opt-in

### Autouse фикстуры (автоматически применяются)

Эти фикстуры применяются автоматически ко всем тестам без явного указания:

#### `session_env_defaults` (scope="session", autouse=True)
- Устанавливает обязательные переменные окружения до импорта модулей проекта
- Применяется один раз на всю сессию тестов
- **Не требует явного указания в тестах**

#### `base_env` (autouse=True)
- Гарантирует наличие обязательных переменных окружения для каждого теста
- Создаёт изолированные хранилища
- **Не требует явного указания в тестах**

#### `patch_models_store` (autouse=True)
- Подменяет ModelsStore на in-memory реализацию для unit-тестов
- Автоматически отключается для тестов с маркерами `db`, `integration`, `e2e`, `celery`, `infra`
- **Не требует явного указания в тестах**

**Правило:** Autouse фикстуры должны использоваться только для базовых настроек окружения, которые нужны всем тестам.

### Opt-in фикстуры (требуют явного указания)

Эти фикстуры нужно явно указывать в параметрах теста:

#### `cleanup_tables` (scope="function")
- Очищает таблицы PostgreSQL перед тестом (TRUNCATE)
- Используется для тестов с проверкой commit'ов
- **Требует явного указания:** `async def test_something(cleanup_tables):`

**Пример:**
```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_chats_store(cleanup_tables):
    """Тест с явным указанием фикстуры cleanup_tables."""
    store = ChatsStore()
    await store.add_chat(12345)
```

#### `postgres_transaction` (scope="function")
- Использует транзакционный rollback для изоляции тестов
- Быстрее, чем TRUNCATE, но не подходит для тестов с commit'ами
- **Требует явного указания:** `async def test_something(postgres_transaction):`

**Пример:**
```python
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.asyncio
async def test_quick_db_test(postgres_transaction):
    """Быстрый тест с транзакционным rollback."""
    store = ChatsStore()
    await store.add_chat(12345)
```

#### `celery_test_queues` (scope="function")
- Создаёт изолированные тестовые очереди Celery
- Используется для E2E тестов с Celery
- **Требует явного указания:** `def test_celery(celery_test_queues):`

**Пример:**
```python
@pytest.mark.e2e
@pytest.mark.celery
def test_celery_task(celery_test_queues, celery_worker_ready):
    """E2E тест с Celery."""
    result = celery_app_test.send_task('test.ping')
    assert result.get(timeout=5) == "pong"
```

#### `reset_singletons` (scope="function", autouse=False)
- Сбрасывает состояние синглтонов (CeleryServices, DispatchRegistry и др.)
- Используется для тестов, которые мутируют состояние синглтонов
- **Требует явного указания:** `def test_something(reset_singletons):`

**Пример:**
```python
@pytest.mark.unit
def test_celery_services(reset_singletons):
    """Тест с сбросом синглтонов."""
    # тест, который мутирует CeleryServices
```

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

## Добавление нового теста

- Создайте файл в `tests/` по структуре модулей.
- Для async-тестов: `@pytest.mark.asyncio`.
- Помечайте зависимости: `@pytest.mark.db`, `@pytest.mark.redis`, `@pytest.mark.celery`, `@pytest.mark.slow` по необходимости.
- Используйте правильные маркеры (см. раздел "Правила использования маркеров").
- Выбирайте правильные фикстуры (autouse применяются автоматически, opt-in нужно указывать явно).

## Покрытие

### Coverage threshold

**Что это такое:**
Coverage threshold — это минимальный порог покрытия кода тестами. Если покрытие падает ниже порога, тесты завершаются с ошибкой, даже если все тесты прошли успешно.

**Текущий порог:**
- **50%** для unit и integration тестов
- Устанавливается через флаг `--cov-fail-under=50` в pytest

**Где используется:**
- `make test-integration-containers` — проверяет покрытие ≥ 50%
- `make test-integration-containers-xdist` — проверяет покрытие ≥ 50%
- CI pipeline (`.github/workflows/pytest-check.yml`) — проверяет покрытие для unit и integration

**Что происходит при падении ниже порога:**
```bash
$ make test-integration-containers
...
---------- coverage: platform linux, python 3.11 -----------
Name                                    Stmts   Miss  Cover
-----------------------------------------------------------
bot/handlers.py                           120     60    50%
services/prompt_generator.py               85     50    41%  # <-- низкое покрытие
...
-----------------------------------------------------------
TOTAL                                     450    250    44%  # <-- ниже порога 50%

FAIL Required test coverage of 50% not reached. Total coverage: 44.44%
```

**Как исправить:**
1. Добавить тесты для модулей с низким покрытием
2. Убедиться, что все важные ветки кода покрыты тестами
3. Проверить, что тесты действительно запускаются (не пропущены через `skip`)

**Отчёты:**
- Интеграционный прогон: `make test-integration-containers` (создаёт `coverage.xml`, `junit.xml`)
- E2E отчёт: `make test-e2e` (создаёт `junit-e2e.xml`, без coverage)

## Конфигурация подключения к PostgreSQL

Тесты автоматически определяют окружение (Docker контейнер vs локальное) и устанавливают правильный `POSTGRES_HOST`:

- **В Docker контейнере**: используется `postgres_test` (имя сервиса из `tests/docker-compose.test.yml`)
- **Локально**: используется `localhost`

**Как это работает:**

1. `conftest.py` определяет окружение через:
   - Наличие файла `/.dockerenv` (создаётся Docker при запуске контейнера)
   - Переменную окружения `TESTING="1"` (устанавливается в `tests/docker-compose.test.yml`)

2. Если тесты запускаются в Docker и `POSTGRES_HOST` уже установлен (из `tests/docker-compose.test.yml`), он не перезаписывается.

3. Если PostgreSQL недоступен, тесты пропускаются с понятным сообщением:
   - В Docker: "PostgreSQL недоступен по адресу postgres_test:5432. Убедитесь, что контейнер postgres_test запущен..."
   - Локально: "PostgreSQL недоступен по адресу localhost:5432. Убедитесь, что PostgreSQL запущен локально..."

**Важно:**

- Для запуска integration тестов с PostgreSQL используйте `make test-integration-containers` (автоматически поднимает контейнеры)
- Для локального запуска убедитесь, что PostgreSQL запущен на `localhost:5432` или используйте `make test-up`

## Изоляция тестов с PostgreSQL

Для тестов, которые работают с PostgreSQL, доступны два подхода к изоляции:

### 1. `cleanup_tables` (TRUNCATE) — для тестов с проверкой commit'ов

Используйте фикстуру `cleanup_tables` для тестов, которые проверяют commit'ы в БД или используют несколько соединений из пула.

**Преимущества:**
- Работает с любым количеством соединений из пула
- Подходит для тестов, которые проверяют commit'ы
- Гарантирует полную очистку таблиц

**Недостатки:**
- Медленнее, чем транзакционный rollback
- Требует выполнения TRUNCATE для каждой таблицы

**Пример использования:**
```python
@pytest.mark.asyncio
async def test_something(cleanup_tables):
    # тест использует БД, все таблицы очищены перед тестом
    store = ChatsStore()
    await store.add_chat(12345)
    # изменения закоммичены и останутся после теста
```

### 2. `postgres_transaction` (ROLLBACK) — для быстрых тестов

Используйте фикстуру `postgres_transaction` для быстрых тестов без проверки commit'ов.

**Преимущества:**
- Быстрее, чем TRUNCATE
- Автоматический откат всех изменений после теста

**Недостатки:**
- Не подходит для тестов, которые проверяют commit'ы
- Может не работать корректно с параллельными операциями из разных соединений

**Пример использования:**
```python
@pytest.mark.asyncio
async def test_something(postgres_transaction):
    # тест использует БД, все изменения будут откачены после теста
    store = ChatsStore()
    await store.add_chat(12345)
    # изменения будут откачены автоматически
```

**Рекомендации:**
- Для большинства тестов используйте `cleanup_tables`
- Используйте `postgres_transaction` только для простых тестов без проверки commit'ов

## E2E тесты для Celery

E2E тесты для Celery требуют запущенных контейнеров с worker:

```bash
# Запуск тестовых контейнеров (Postgres, Redis, Celery Worker)
make test-up

# Запуск только поведенческих E2E тестов Celery (без infra-набора)
make test-e2e

# Или вручную:
docker compose --env-file tests/.env.test -f tests/docker-compose.test.yml up -d --build
export $(grep -v '^[[:space:]]*#' tests/.env.test | grep -v '^[[:space:]]*$' | xargs) && pytest -m "e2e and not infra"
docker compose -f tests/docker-compose.test.yml down -v
```

**Важно:**
- Используется отдельный тестовый Celery app (`tests.common.celery_app_test`) с тестовыми очередями
- Тестовый Celery app изолирован от боевого кода и использует только тестовый конфиг (`utils.config_test`)
- Pytest fixture `celery_worker_ready` (в `tests/fixtures/celery_worker_ready.py`) автоматически проверяет готовность worker через `test.ping`
- Worker запускается с тестовыми очередями: `test_main`, `test_images`, `test_maintenance`
- Логирование в тестах идёт только в stdout (нет файловых логов)

**Структура Celery-тестов:**
- `tests/e2e/celery/test_celery_e2e_basic.py` — короткий поведенческий e2e‑набор (`@pytest.mark.e2e`):
  - отправка `test.ping` и ожидание `"pong"`;
  - проверка работы result backend;
  - конкурентное выполнение нескольких задач.
- `tests/test_services/test_celery_e2e.py` — инфраструктурные/диагностические тесты Celery:
  - помечены как `@pytest.mark.e2e` + `@pytest.mark.infra`;
  - по умолчанию не попадают в `make test-e2e` (фильтрация `e2e and not infra`).

**Запуск infra-набора (по необходимости):**

```bash
make test-up
export $(grep -v '^[[:space:]]*#' tests/.env.test | grep -v '^[[:space:]]*$' | xargs) && pytest -m "e2e and infra"
make test-down
```

## Запуск в CI

Тесты автоматически выполняются при каждом `push` и `pull request` через GitHub Actions.
