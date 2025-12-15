Схема структурированного логирования для Loki и Promtail
========================================================

Версия схемы: `v1`

Этот документ описывает полную схему структурированных JSON‑логов проекта Wednesday Frog Bot, которые собираются Promtail и отправляются в Loki для эффективного поиска, анализа и мониторинга.

## 1. Обзор структуры лога

### 1.1. Формат логирования

Проект использует **JSON-формат** для структурированного логирования через библиотеку `loguru` с параметром `serialize=True`.

**Основной поток логирования:**
- Логи пишутся в **stdout** (обязательный sink) в формате JSON
- Опционально (если `LOG_TO_FILE=true`): дублирование в файл `logs/wednesday_bot.events.jsonl`
- Promtail читает логи из **Docker контейнеров** (stdout/stderr через Docker JSON-file driver)
- Promtail парсит JSON, извлекает поля и создаёт Loki labels
- Логи отправляются в Loki для хранения и индексации

### 1.2. Структура JSON-записи

Loguru с `serialize=True` создаёт JSON с обёрткой `record`:

```json
{
  "record": {
    "time": {
      "repr": "2025-12-03T21:15:42.123456+03:00",
      "timestamp": 1701628542.123456
    },
    "level": {
      "name": "INFO",
      "no": 20
    },
    "message": "Начинаю генерацию изображения жабы",
    "extra": {
      "event": "generation_started",
      "service": "wednesday-bot",
      "env": "production",
      "user_id": "123456789",
      "status": "started"
    },
    "file": {
      "name": "services/image_generator.py",
      "path": "/app/services/image_generator.py"
    },
    "function": "generate_frog_image",
    "line": 260,
    "module": "services.image_generator",
    "name": "services.image_generator",
    "process": {
      "id": 1,
      "name": "MainProcess"
    },
    "thread": {
      "id": 140234567890,
      "name": "MainThread"
    }
  }
}
```

### 1.3. Обработка Promtail

Promtail читает логи из Docker контейнеров (`/var/lib/docker/containers/*/*-json.log`) и применяет pipeline:

1. **`docker: {}`** — парсит Docker JSON-file формат (извлекает поле `log` с JSON-строкой)
2. **`json`** — парсит JSON из поля `log`, извлекает базовые поля
3. **`json` со `source: extra`** — извлекает структурированные поля из `extra`
4. **`timestamp`** — устанавливает timestamp записи в Loki
5. **`labels`** — поднимает низкокардинальные поля в Loki labels

## 2. Обязательные поля (Standard Fields)

Каждая запись лога содержит следующие стандартные поля, автоматически добавляемые `loguru`:

### 2.1. Временные метки

- **`time.repr: str`** — таймстемп события в ISO‑формате с таймзоной (RFC3339/ISO8601)  
  Пример: `"2025-12-03T21:15:42.123456+03:00"`  
  **Используется Promtail** для установки timestamp записи в Loki.

- **`time.timestamp: float`** — Unix timestamp (опционально, для совместимости)

### 2.2. Уровень логирования

- **`level.name: str`** — строковое имя уровня логирования  
  Возможные значения: `"TRACE"`, `"DEBUG"`, `"INFO"`, `"SUCCESS"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`  
  **Используется как Loki label `level`** (низкая кардинальность).

- **`level.no: int`** — числовой код уровня (10, 20, 25, 30, 40, 50)

### 2.3. Сообщение

- **`message: str`** — человеко‑читаемое сообщение  
  Автоматически обрабатывается функцией `mask_secrets()` для маскировки секретов перед записью.

### 2.4. Информация о месте вызова

- **`file.name: str`** — имя файла (например, `"image_generator.py"`)
- **`file.path: str`** — полный путь к файлу
- **`function: str`** — имя функции/метода, где произошло логирование
- **`line: int`** — номер строки в файле
- **`module: str`** — имя модуля (например, `"services.image_generator"`)
- **`name: str`** — имя логгера (обычно совпадает с `module`)

### 2.5. Информация о процессе

- **`process.id: int`** — ID процесса
- **`process.name: str`** — имя процесса
- **`thread.id: int`** — ID потока
- **`thread.name: str`** — имя потока

### 2.6. Дополнительные поля (`extra`)

Объект `extra` содержит структурированные поля события, добавленные через:
- `log_event()` — структурированное логирование событий
- `logger.bind()` — привязка контекстных полей
- `log_http()` — логирование HTTP-запросов
- `log_worker()` — логирование Celery задач

**Важно:** Все значения в `extra` автоматически обрабатываются функцией `scrub()` для маскировки секретов.

## 3. Ключевые поля-метки (Loki Labels)

Loki labels используются для индексации и быстрого поиска. **Важно:** в качестве labels должны использоваться только **низкокардинальные поля** (ограниченное количество уникальных значений).

### 3.1. Текущие Loki Labels

В текущей конфигурации Promtail следующие поля поднимаются в Loki labels:

| Label | Источник | Описание | Кардинальность |
|-------|----------|----------|----------------|
| `service` | `extra.service` или статический label | Имя сервиса (например, `"wednesday-bot"`, `"celery_worker"`) | Низкая (2-5 значений) |
| `env` | `extra.env` или статический label | Окружение (`"dev"`, `"staging"`, `"production"`) | Низкая (2-4 значения) |
| `level` | `level.name` | Уровень логирования (`"INFO"`, `"ERROR"`, `"WARNING"`) | Низкая (5-7 значений) |

### 3.2. Поля, которые НЕ используются как Labels

Следующие поля имеют **высокую кардинальность** и остаются только в теле лога для поиска через LogQL:

- **`user_id`** — идентификатор пользователя (множество уникальных значений)
- **`prompt_hash`** — SHA-256 хэш промпта (64-символьный hex, практически уникален)
- **`image_id`** — идентификатор изображения (высокая кардинальность)
- **`task_id`** — идентификатор Celery задачи (уникален для каждой задачи)
- **`request_id`** — идентификатор HTTP-запроса (уникален для каждого запроса)
- **`message`** — текст сообщения (практически уникален)
- **`timestamp`** — временная метка (уникальна для каждой записи)

**Почему это важно:** Высококардинальные labels создают огромное количество уникальных комбинаций в Loki, что приводит к:
- Резкому увеличению потребления памяти
- Замедлению запросов
- Проблемам с производительностью индексации

### 3.3. Рекомендации по добавлению новых Labels

При добавлении нового поля в качестве Loki label убедитесь, что:

1. **Кардинальность низкая** — количество уникальных значений ограничено (желательно < 100)
2. **Значения стабильны** — не меняются часто и не содержат динамических данных
3. **Полезны для фильтрации** — часто используются в LogQL запросах для фильтрации

**Примеры хороших candidates для labels:**
- `event` — тип события (`"generation_started"`, `"celery_task"`, `"http_request"`) — **может быть добавлен**
- `status` — статус операции (`"ok"`, `"error"`, `"started"`) — **может быть добавлен**
- `handler` — имя обработчика команды (`"frog_command"`, `"start_command"`) — **может быть добавлен**

**Примеры плохих candidates:**
- `user_id` — слишком много уникальных значений
- `prompt_hash` — практически уникален для каждого промпта
- `latency_ms` — числовое значение, лучше использовать в метриках

## 4. Поля, специфичные для бота

### 4.1. Поля событий (`log_event`)

Функция `utils.logger.log_event()` автоматически добавляет следующие поля в `extra`:

#### Базовые поля событий

- **`event: str`** — тип/код события  
  Примеры: `"generation_started"`, `"generation_caption_selected"`, `"image_cache_hit"`, `"celery_task"`, `"http_request"`, `"unhandled_exception"`

- **`status: str`** — статус события  
  Возможные значения: `"ok"`, `"error"`, `"started"`, `"in_progress"`, `"cached"`, `"circuit_breaker_open"`, `"fallback_static"`, `"missing_file"`

- **`service: str`** — имя сервиса  
  Значение из переменной окружения `SERVICE_NAME` или `"wednesday-bot"` по умолчанию

- **`env: str`** — окружение  
  Значение из переменной окружения `ENV` или `"dev"` по умолчанию

#### Поля, связанные с пользователями

- **`user_id: str`** — идентификатор пользователя Telegram (приведён к строке)  
  Может отсутствовать для системных событий.  
  **Не используется как Loki label** из-за высокой кардинальности.

#### Поля, связанные с генерацией изображений

- **`prompt_hash: str`** — SHA‑256 хэш промпта (64‑символьный hex)  
  Используется для кеширования и дедупликации.  
  **Не используется как Loki label** из-за высокой кардинальности.

- **`image_id: str`** — идентификатор/хэш изображения  
  Может быть SHA-256 хэшем или другим уникальным идентификатором.  
  **Не используется как Loki label** из-за высокой кардинальности.

#### Поля производительности

- **`latency_ms: float`** — латентность операции в миллисекундах  
  Используется для мониторинга производительности.  
  **Не используется как Loki label** (лучше использовать в метриках Prometheus).

### 4.2. Поля Celery задач (`log_worker`)

Функция `utils.logger.log_worker()` добавляет следующие поля:

- **`task_name: str`** — имя задачи Celery (например, `"generate_frog_image_task"`)
- **`task_id: str`** — уникальный идентификатор задачи Celery  
  **Не используется как Loki label** из-за высокой кардинальности.

### 4.3. Поля HTTP-запросов (`log_http`)

Функция `utils.logger.log_http()` добавляет следующие поля:

- **`method: str`** — HTTP-метод (`"GET"`, `"POST"`, `"PUT"`, `"DELETE"` и т.д.)
- **`path: str`** — путь запроса (например, `"/api/v1/generate"`)
- **`status_code: int`** — HTTP статус-код ответа (200, 404, 500 и т.д.)

**Потенциальные поля для будущего использования:**

- **`request_id: str`** — уникальный идентификатор запроса (для трейсинга)  
  Может быть добавлен в будущем для корреляции запросов.  
  **Не используется как Loki label** из-за высокой кардинальности.

- **`api_endpoint: str`** — имя API endpoint'а  
  Может быть добавлен для группировки запросов к одному endpoint'у.  
  **Может быть использован как Loki label**, если кардинальность низкая.

### 4.4. Поля обработчиков бота

В обработчиках команд (`bot/handlers.py`) могут использоваться следующие поля:

- **`handler: str`** — имя обработчика команды  
  Примеры: `"frog_command"`, `"start_command"`, `"status_command"`  
  **Может быть использован как Loki label**, если кардинальность низкая.

- **`chat_id: str`** — идентификатор чата Telegram  
  Может использоваться для групповых чатов.  
  **Не используется как Loki label** из-за высокой кардинальности (но ниже, чем `user_id`).

### 4.5. Дополнительные поля (`extra`)

Любые дополнительные поля могут быть переданы через параметр `extra` в функциях логирования:

```python
log_event(
    event="custom_event",
    extra={
        "custom_field": "value",
        "attempt": 3,
        "max_retries": 5,
        "error": "Connection timeout"
    }
)
```

**Важно:** Все значения в `extra` автоматически обрабатываются функцией `scrub()` для маскировки секретов по ключевым словам (`token`, `password`, `secret`, `api_key` и т.д.).

## 5. Примеры использования

### 5.1. Пример JSON-лога

Полный пример структурированного JSON-лога:

```json
{
  "record": {
    "time": {
      "repr": "2025-12-14T15:30:45.123456+03:00",
      "timestamp": 1702564245.123456
    },
    "level": {
      "name": "INFO",
      "no": 20
    },
    "message": "Начинаю генерацию изображения жабы",
    "extra": {
      "event": "generation_started",
      "service": "wednesday-bot",
      "env": "production",
      "user_id": "123456789",
      "status": "started"
    },
    "file": {
      "name": "services/image_generator.py",
      "path": "/app/services/image_generator.py"
    },
    "function": "generate_frog_image",
    "line": 260,
    "module": "services.image_generator",
    "name": "services.image_generator",
    "process": {
      "id": 1,
      "name": "MainProcess"
    },
    "thread": {
      "id": 140234567890,
      "name": "MainThread"
    }
  }
}
```

Пример лога с кешированием изображения:

```json
{
  "record": {
    "time": {
      "repr": "2025-12-14T15:30:46.234567+03:00",
      "timestamp": 1702564246.234567
    },
    "level": {
      "name": "INFO",
      "no": 20
    },
    "message": "Изображение найдено в кеше",
    "extra": {
      "event": "image_cache_hit",
      "service": "wednesday-bot",
      "env": "production",
      "user_id": "123456789",
      "prompt_hash": "a1b2c3d4e5f6...",
      "image_id": "f6e5d4c3b2a1...",
      "latency_ms": 0.0,
      "status": "ok"
    },
    "module": "services.image_generator",
    "function": "generate_frog_image",
    "line": 366
  }
}
```

Пример лога Celery задачи:

```json
{
  "record": {
    "time": {
      "repr": "2025-12-14T15:30:47.345678+03:00",
      "timestamp": 1702564247.345678
    },
    "level": {
      "name": "INFO",
      "no": 20
    },
    "message": "Task generate_frog_image_task (abc123) ok",
    "extra": {
      "event": "celery_task",
      "service": "wednesday-bot",
      "env": "production",
      "task_name": "generate_frog_image_task",
      "task_id": "abc123-def456-ghi789",
      "status": "ok",
      "latency_ms": 1250.5
    },
    "module": "services.celery_tasks",
    "function": "generate_frog_image_task",
    "line": 300
  }
}
```

### 5.2. Примеры LogQL-запросов

#### Поиск всех ошибок генерации изображений

```logql
{service="wednesday-bot", level="ERROR"}
  | json
  | extra.event="generation_attempt_failed"
```

#### Поиск событий конкретного пользователя

```logql
{service="wednesday-bot"}
  | json
  | extra.user_id="123456789"
```

#### Поиск успешных генераций с высокой латентностью

```logql
{service="wednesday-bot", level="INFO"}
  | json
  | extra.event="generation_api_ok"
  | extra.latency_ms > 5000
```

#### Поиск всех Celery задач, которые завершились с ошибкой

```logql
{service="wednesday-bot"}
  | json
  | extra.event="celery_task"
  | extra.status="error"
```

#### Поиск событий кеширования

```logql
{service="wednesday-bot"}
  | json
  | extra.event="image_cache_hit"
```

#### Поиск событий с использованием конкретного промпта

```logql
{service="wednesday-bot"}
  | json
  | extra.prompt_hash="a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456"
```

#### Агрегация по типу события за последний час

```logql
sum by (event) (
  count_over_time(
    {service="wednesday-bot"}
    | json
    | extra.event != ""
    [1h]
  )
)
```

#### Поиск событий с circuit breaker

```logql
{service="wednesday-bot"}
  | json
  | extra.event=~"circuit_breaker.*"
```

#### Поиск всех HTTP-запросов с ошибками

```logql
{service="wednesday-bot"}
  | json
  | extra.event="http_request"
  | extra.status_code >= 400
```

#### Поиск событий в production окружении

```logql
{service="wednesday-bot", env="production"}
  | json
```

#### Поиск всех генераций конкретного пользователя за период

```logql
{service="wednesday-bot"}
  | json
  | extra.user_id="123456789"
  | extra.event=~"generation.*"
  | timestamp >= now() - 24h
```

#### Корреляция событий по task_id или request_id

```logql
# Поиск всех событий для конкретной Celery задачи
{service="wednesday-bot"}
  | json
  | extra.task_id="abc123-def456-ghi789"
```

```logql
# Поиск всех событий для конкретного HTTP-запроса (если request_id добавлен)
{service="wednesday-bot"}
  | json
  | extra.request_id="req-123456789"
```

#### Анализ паттернов генераций по времени

```logql
# Подсчет генераций по часам за последние 24 часа
sum by (hour) (
  count_over_time(
    {service="wednesday-bot"}
      | json
      | extra.event="generation_api_ok"
      [24h]
  )
)
```

#### Анализ производительности генераций (топ-10 самых медленных)

```logql
topk(10,
  sum by (user_id) (
    {service="wednesday-bot"}
      | json
      | extra.event="generation_api_ok"
      | extra.latency_ms > 0
      | extra.latency_ms > 5000
      [1h]
  )
)
```

Этот запрос показывает топ-10 пользователей с самыми медленными генерациями (>5 секунд) за последний час.

### 5.3. Типичные сценарии отладки

#### Поиск всех ошибок за последний час с группировкой по типу

```logql
sum by (event, status) (
  count_over_time(
    {service="wednesday-bot", level="ERROR"}
      | json
      | extra.event != ""
      | extra.status != ""
      [1h]
  )
)
```

Этот запрос показывает количество ошибок по типам событий и статусам за последний час, что помогает быстро выявить проблемные области.

#### Корреляция событий по user_id и task_id

```logql
# Поиск всех событий для конкретного пользователя и связанных Celery задач
{service="wednesday-bot"}
  | json
  | extra.user_id="123456789"
  | extra.task_id != ""
```

```logql
# Поиск всех событий для конкретной Celery задачи с привязкой к пользователю
{service="wednesday-bot"}
  | json
  | extra.task_id="abc123-def456-ghi789"
  | extra.user_id != ""
```

Эти запросы помогают отследить полный путь выполнения операции от запроса пользователя до завершения Celery задачи.

#### Мониторинг Circuit Breaker срабатываний

```logql
# Поиск всех срабатываний Circuit Breaker
{service="wednesday-bot"}
  | json
  | extra.event=~"circuit_breaker.*"
```

```logql
# Подсчет срабатываний Circuit Breaker по типам за последний час
sum by (event) (
  count_over_time(
    {service="wednesday-bot"}
      | json
      | extra.event=~"circuit_breaker.*"
      [1h]
  )
)
```

```logql
# Поиск событий с открытым Circuit Breaker (статус "circuit_breaker_open")
{service="wednesday-bot"}
  | json
  | extra.status="circuit_breaker_open"
```

Эти запросы помогают отслеживать состояние Circuit Breaker и выявлять проблемы с доступностью внешних API (Kandinsky, GigaChat).

#### Диагностика проблем с генерацией изображений

```logql
# Поиск всех неудачных попыток генерации с деталями ошибок
{service="wednesday-bot", level="ERROR"}
  | json
  | extra.event=~"generation.*"
  | extra.status="error"
```

```logql
# Анализ успешности генераций по времени (для выявления паттернов)
sum by (status) (
  count_over_time(
    {service="wednesday-bot"}
      | json
      | extra.event=~"generation.*"
      | extra.status != ""
      [1h]
  )
)
```

#### Отслеживание проблем с Celery задачами

```logql
# Поиск всех неудачных Celery задач с деталями
{service="celery-worker", level="ERROR"}
  | json
  | extra.event="celery_task"
  | extra.status="error"
```

```logql
# Анализ производительности Celery задач (топ-10 самых медленных)
topk(10,
  sum by (task_name) (
    {service="celery-worker"}
      | json
      | extra.event="celery_task"
      | extra.latency_ms > 0
      | extra.latency_ms > 30000
      [1h]
  )
)
```

#### Анализ rate limiting

```logql
# Поиск всех событий, связанных с rate limiting
{service="wednesday-bot"}
  | json
  | message=~".*rate.*limit.*"
```

```logql
# Подсчет срабатываний rate limit по пользователям
sum by (user_id) (
  count_over_time(
    {service="wednesday-bot"}
      | json
      | message=~".*rate.*limit.*"
      | extra.user_id != ""
      [1h]
  )
)
```

### 5.4. Использование logfmt для поиска

Promtail также поддерживает извлечение полей через `logfmt`. Если в будущем будет использоваться logfmt-формат, можно использовать:

```logql
{service="wednesday-bot"}
  | logfmt
  | user_id="123456789"
```

## 6. Гарантии по безопасности

### 6.1. Маскировка секретов

Все секреты автоматически маскируются перед записью в лог:

1. **`mask_secrets()`** — маскирует известные секретные значения (GigaChat authorization key, Redis password, Postgres password) в строках, заменяя их на `"****"`

2. **`scrub()`** — рекурсивно обрабатывает структурированные данные (`dict`, `list`, `tuple`, `set`):
   - Маскирует значения по ключам, содержащим чувствительные слова (`token`, `secret`, `password`, `api_key`, `authorization`, `bearer` и т.д.)
   - Рекурсивно обрабатывает вложенные структуры
   - Для строк дополнительно вызывает `mask_secrets()`

**Список чувствительных ключевых слов:**
- `token`, `secret`, `password`, `passwd`
- `api_key`, `apikey`, `authorization`, `bearer`
- `access_token`, `refresh_token`
- `client_secret`, `private_key`, `secret_key`
- `cookie`, `set-cookie`

### 6.2. Обработка в Promtail/Loki

Promtail и Loki **не выполняют** дополнительного агрессивного «вырезания» секретов, чтобы:
- Не дублировать логику маскировки
- Не усложнять отладку
- Сохранить структуру логов для анализа

### 6.3. Дополнительные меры защиты

- **Алёрты** по подозрительным паттернам в логах (например, `Authorization`, `Bearer`, `BEGIN_PRIVATE_KEY`)
- **Операционные правила:**
  - Не логировать конфигурацию/env целиком
  - Не логировать тела запросов с секретами
  - Использовать структурированное логирование вместо строковых конкатенаций

## 7. Конфигурация Promtail

Текущая конфигурация Promtail (`monitoring/promtail-config.yml`):

```yaml
scrape_configs:
  - job_name: wednesday-logs
    static_configs:
      - targets:
          - localhost
        labels:
          job: wednesday-logs
          __path__: /var/lib/docker/containers/*/*-json.log
    pipeline_stages:
      # 1. Парсим docker json-file формат
      - docker: {}

      # 2. Парсим JSON из поля log
      - json:
          expressions:
            timestamp: timestamp
            level: level
            message: message
            extra: extra

      # 3. Извлекаем service и env из extra
      - json:
          source: extra
          expressions:
            service: service
            env: env
            event: event
            status: status

      # 4. Устанавливаем timestamp
      - timestamp:
          source: timestamp
          format: RFC3339

      # 5. Поднимаем только low-cardinality labels
      - labels:
          service:
          env:
          level:
```

**Примечание:** В текущей конфигурации `event` и `status` извлекаются из `extra`, но **не поднимаются в labels**. Это может быть изменено в будущем, если кардинальность этих полей окажется приемлемой.

## 8. Эволюция схемы

### 8.1. Версионирование

- Текущая версия схемы: **`v1`**
- При значительных изменениях схемы версия должна быть обновлена

### 8.2. Добавление новых полей

При добавлении новых полей в `extra`:

1. **Обновить этот документ** — описать имя, тип и назначение поля
2. **Оценить кардинальность** — решить, можно ли использовать поле как Loki label
3. **Обновить Promtail pipeline** — если поле нужно в качестве label, добавить соответствующий stage
4. **Обновить примеры LogQL** — добавить примеры использования нового поля

### 8.3. Изменение структуры JSON

При изменении структуры JSON (например, смена поля `time` или формата timestamp):

1. **Обновить `timestamp` stage в Promtail** — убедиться, что timestamp корректно извлекается
2. **Проверить запросы и дашборды в Grafana** — убедиться, что существующие запросы продолжают работать
3. **Обновить версию схемы** — если изменения breaking

### 8.4. Рекомендации по расширению

**Потенциальные улучшения:**

1. **Добавить `event` и `status` в Loki labels** — если кардинальность окажется приемлемой
2. **Добавить `handler` в Loki labels** — для фильтрации по обработчикам команд
3. **Добавить `task_name` в Loki labels** — для фильтрации по типам Celery задач
4. **Добавить `request_id`** — для трейсинга запросов (но не как label)
5. **Добавить `api_endpoint`** — для группировки HTTP-запросов (возможно как label)

## 9. Справочная информация

### 9.1. Основные функции логирования

- **`log_event()`** — структурированное логирование событий с автоматической маскировкой секретов
- **`log_http()`** — логирование HTTP-запросов с метриками
- **`log_worker()`** — логирование Celery задач
- **`get_logger()`** — получение логгера для модуля
- **`logger.bind()`** — привязка контекстных полей к логгеру

### 9.2. Связанные документы

- `utils/logger.py` — исходный код модуля логирования
- `monitoring/promtail-config.yml` — конфигурация Promtail
- `docs/MONITORING.md` — общая документация по мониторингу

### 9.3. Полезные ссылки

- [LogQL документация](https://grafana.com/docs/loki/latest/logql/)
- [Promtail pipeline stages](https://grafana.com/docs/loki/latest/clients/promtail/stages/)
- [Loguru документация](https://loguru.readthedocs.io/)
