# Тесты проекта

## Быстрый старт (матрица маркеров)

- unit: без внешних зависимостей, без БД/Redis/Celery, без slow.
- integration: с Postgres/Redis, но без Celery e2e/infra.
- e2e: end-to-end сценарии; infra — диагностические Celery e2e.
- db/redis/celery: ресурсные зависимости; slow — долгие кейсы.

## Команды

- Unit без контейнеров: `make test-unit-no-container`
- Integration с контейнерами: `make test-integration-containers`
- E2E без infra: `make test-e2e`
- Celery infra: `make test-e2e-infra`

## Добавление нового теста

- Создайте файл в `tests/` по структуре модулей.
- Для async-тестов: `@pytest.mark.asyncio`.
- Помечайте зависимости: `@pytest.mark.db`, `@pytest.mark.redis`, `@pytest.mark.celery`, `@pytest.mark.slow` по необходимости.

## Покрытие

- Интеграционный прогон: `make test-integration-containers` (создаёт `coverage.xml`, `junit.xml`).
- E2E отчёт: `make test-e2e` (создаёт `junit-e2e.xml`).
- **Coverage threshold:** Минимальный порог покрытия кода установлен на 50% для unit и integration тестов. Если покрытие ниже порога, тесты завершаются с ошибкой.

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
docker compose --env-file .env.test -f docker-compose.test.yml up -d --build
export $(grep -v '^[[:space:]]*#' .env.test | grep -v '^[[:space:]]*$' | xargs) && pytest -m "e2e and not infra"
docker compose -f docker-compose.test.yml down -v
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
export $(grep -v '^[[:space:]]*#' .env.test | grep -v '^[[:space:]]*$' | xargs) && pytest -m "e2e and infra"
make test-down
```

## Запуск в CI

Тесты автоматически выполняются при каждом `push` и `pull request` через GitHub Actions.
