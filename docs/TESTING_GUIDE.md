# Руководство по написанию тестов

Этот документ содержит детальные правила написания тестов для проекта Wednesday Frog Bot.

## Содержание

1. [Маркеры тестов](#маркеры-тестов)
2. [Фикстуры: autouse vs opt-in](#фикстуры-autouse-vs-opt-in)
3. [Правила написания тестов](#правила-написания-тестов)
4. [CI/Pre-commit проверки](#cipre-commit-проверки)

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
