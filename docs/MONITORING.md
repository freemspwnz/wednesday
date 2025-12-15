# Руководство по мониторингу Wednesday Frog Bot

Данное руководство описывает полный стек наблюдаемости (Observability Stack) для Wednesday Frog Bot, включая метрики, логи и алерты.

## Содержание

1. [Обзор стека наблюдаемости](#обзор-стека-наблюдаемости)
2. [Мониторинг метрик (Prometheus & Grafana)](#мониторинг-метрик-prometheus--grafana)
3. [Логирование (Loki & Promtail)](#логирование-loki--promtail)
4. [Алерты (Alerting)](#алерты-alerting)
5. [Конфигурация](#конфигурация)

---

## Обзор стека наблюдаемости

### Компоненты стека

Wednesday Frog Bot использует современный стек наблюдаемости на основе открытых инструментов:

- **Prometheus** — сбор и хранение метрик
- **Grafana** — визуализация метрик и логов
- **Loki** — агрегация и хранение логов
- **Promtail** — сбор логов из контейнеров

### Архитектура интеграции

Все компоненты мониторинга интегрированы с Docker Compose через отдельный файл `docker-compose.monitoring.yml` или включены в основной `docker-compose.yml`. Компоненты работают в изолированной сети `monitoring` и взаимодействуют с приложением через внутренние порты.

**Схема потока данных:**

```
┌─────────────────┐
│  Wednesday Bot  │
│  (bot, celery-  │
│   worker, beat) │
└────────┬────────┘
         │
         ├─── Метрики (Prometheus Exporter) ───> Prometheus ───> Grafana
         │
         └─── Логи (stdout JSON) ───> Docker JSON Logs ───> Promtail ───> Loki ───> Grafana
```

### Docker Compose интеграция

В `docker-compose.yml` определены следующие сервисы мониторинга:

- **prometheus** — сбор метрик с endpoints `/metrics` от всех сервисов
- **loki** — агрегация логов
- **grafana** — визуализация (доступен на `http://localhost:3000`)
- **promtail** — сбор логов из Docker контейнеров

Все сервисы подключены к сети `monitoring` и имеют соответствующие healthcheck'и для контроля готовности.

> 📖 **Подробная информация о работе Celery, архитектуре задач и планировщике** см. в [**ARCHITECTURE.md**](ARCHITECTURE.md)

---

## Мониторинг метрик (Prometheus & Grafana)

### Доступные метрики

Бот экспортирует следующие типы метрик через Prometheus Exporter на порту `8000` (настраивается через `PROMETHEUS_EXPORTER_PORT`):

#### Метрики генерации изображений

- **`frog_generations_total`** (Counter)
  - Описание: Общее количество попыток генерации изображения жабы
  - Labels: `status` (success/failure/skipped), `source` (bot/scheduler)
  - Пример: `frog_generations_total{status="success",source="bot"}`

- **`frog_generation_latency_seconds`** (Histogram)
  - Описание: Латентность успешных генераций в секундах
  - Labels: `status`, `source`
  - Buckets: 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0
  - Пример: `frog_generation_latency_seconds_bucket{le="10.0",status="success",source="bot"}`

- **`frog_generation_queue_length`** (Gauge)
  - Описание: Текущая длина очереди задач на генерацию
  - Labels: `source`
  - Пример: `frog_generation_queue_length{source="bot"}`

#### Метрики Celery задач

- **`celery_tasks_total`** (Counter)
  - Описание: Общее количество Celery задач
  - Labels: `task_name`, `status`
  - Пример: `celery_tasks_total{task_name="wednesday.send_frog",status="success"}`

- **`celery_task_duration_seconds`** (Histogram)
  - Описание: Длительность выполнения Celery задач в секундах
  - Labels: `task_name`
  - Buckets: 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0
  - Пример: `celery_task_duration_seconds_bucket{task_name="wednesday.send_frog",le="30.0"}`

- **`celery_task_retries_total`** (Counter)
  - Описание: Количество retry-попыток для Celery задач
  - Labels: `task_name`

- **`celery_task_failures_total`** (Counter)
  - Описание: Количество неудачных Celery задач
  - Labels: `task_name`, `error_type`

- **`celery_queue_length`** (Gauge)
  - Описание: Текущая длина очереди Celery
  - Labels: `queue_name`
  - Пример: `celery_queue_length{queue_name="wednesday"}`

- **`celery_active_tasks`** (Gauge)
  - Описание: Количество активных задач в Celery worker
  - Labels: `worker_name`

#### Метрики HTTP retry

- **`http_retries_total`** (Counter)
  - Описание: Общее количество retry-попыток для HTTP-запросов
  - Labels: `service` (kandinsky/gigachat), `method`, `status` (retry/failed)

- **`http_retry_wait_seconds`** (Histogram)
  - Описание: Время ожидания между retry-попытками в секундах
  - Labels: `service`, `method`
  - Buckets: 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0

#### Стандартные метрики Prometheus

- **`up`** — доступность target'а (1 = доступен, 0 = недоступен)
- **`process_cpu_seconds_total`** — использование CPU
- **`process_resident_memory_bytes`** — использование памяти

### Ключевые панели Grafana (Dashboard)

В Grafana настроены следующие дашборды для визуализации метрик:

#### 1. Wednesday App Metrics (`wednesday-app-metrics.json`)

**Графики:**
- **RPS (Requests Per Second)** — скорость генераций по источникам (bot/scheduler)
- **Задержка генерации** — P50, P95, P99 латентности генерации изображений
- **Успешность генераций** — доля успешных/неудачных генераций
- **Очередь генераций** — текущая длина очереди задач

**Метрики:**
- `rate(frog_generations_total[5m])` — RPS генераций
- `histogram_quantile(0.95, rate(frog_generation_latency_seconds_bucket[5m]))` — P95 латентность
- `rate(frog_generations_total{status="failure"}[5m]) / rate(frog_generations_total[5m])` — error rate

#### 2. Wednesday Celery Metrics (`wednesday-celery-metrics.json`)

**Графики:**
- **Очередь Celery** — длина очередей по именам (wednesday/images/maintenance)
- **Активные задачи** — количество одновременно выполняемых задач
- **Длительность задач** — P50, P95, P99 времени выполнения задач
- **Retry и Failures** — количество повторных попыток и ошибок
- **Throughput задач** — скорость обработки задач по типам

**Метрики:**
- `celery_queue_length{queue_name="wednesday"}` — длина очереди
- `celery_active_tasks{worker_name="celery@worker1"}` — активные задачи
- `histogram_quantile(0.95, rate(celery_task_duration_seconds_bucket[5m]))` — P95 длительность

#### 3. Wednesday Retry Metrics (`wednesday-retry-metrics.json`)

**Графики:**
- **HTTP Retry Rate** — частота retry по сервисам (Kandinsky/GigaChat)
- **Retry Wait Time** — время ожидания между попытками
- **Failed Retries** — количество исчерпанных retry

#### 4. Wednesday Logs Dashboard (`wednesday-logs-dashboard.json`)

**Панели:**
- **Логи по уровням** — распределение логов по severity (ERROR/WARNING/INFO)
- **Логи по сервисам** — количество логов по сервисам (bot/celery-worker/celery-beat)
- **Последние ошибки** — таблица последних ERROR логов с деталями
- **События** — фильтрация по полю `event` (generation, healthcheck, и т.д.)

### SLO (Service Level Objectives)

Рекомендуемые SLO для мониторинга:

#### 1. Доступность генераций

- **Цель:** 99% генераций должны быть успешно обработаны
- **Метрика:** `rate(frog_generations_total{status="success"}[5m]) / rate(frog_generations_total[5m]) >= 0.99`
- **Окно:** 30 дней
- **Алерт:** При падении ниже 95% в течение 5 минут

#### 2. Латентность генераций

- **Цель:** 99% генераций должны быть обработаны менее чем за 30 секунд
- **Метрика:** `histogram_quantile(0.99, rate(frog_generation_latency_seconds_bucket[5m])) < 30`
- **Окно:** 30 дней
- **Алерт:** При P99 > 45 секунд в течение 10 минут

#### 3. Доступность сервиса

- **Цель:** 99.9% uptime сервиса
- **Метрика:** `up{job="bot"} == 1`
- **Окно:** 30 дней
- **Алерт:** При недоступности healthcheck `/health` в течение 2 минут

#### 4. Обработка очереди Celery

- **Цель:** Очередь не должна расти выше 50 задач
- **Метрика:** `celery_queue_length{queue_name="wednesday"} < 50`
- **Окно:** 1 час
- **Алерт:** При превышении 50 задач в течение 5 минут

---

## Логирование (Loki & Promtail)

### Структура логов

Бот использует структурированное логирование через **Loguru** с выводом в JSON формате (при `LOG_TO_FILE=0` логи идут в stdout в JSON).

**Формат лога (JSON):**

```json
{
  "timestamp": "2025-01-15T10:30:45.123456+00:00",
  "level": "INFO",
  "message": "Генерация изображения завершена",
  "name": "services.image_generator",
  "function": "generate_frog_image",
  "line": 245,
  "extra": {
    "service": "wednesday-bot",
    "env": "production",
    "event": "generation",
    "status": "success",
    "user_id": 123456789,
    "chat_id": -1001234567890,
    "latency_ms": 1250.5,
    "source": "bot"
  }
}
```

**Основные поля:**

- **`timestamp`** — время события в формате RFC3339
- **`level`** — уровень логирования (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- **`message`** — текстовое сообщение
- **`name`** — имя модуля (например, `bot.handlers`, `services.image_generator`)
- **`function`** — имя функции
- **`line`** — номер строки
- **`extra`** — дополнительные структурированные данные:
  - `service` — имя сервиса (wednesday-bot/celery-worker/celery-beat)
  - `env` — окружение (production/staging/development)
  - `event` — тип события (generation/healthcheck/dispatch)
  - `status` — статус операции (success/failure/retry)
  - `user_id` — ID пользователя Telegram (если применимо)
  - `chat_id` — ID чата Telegram (если применимо)
  - `latency_ms` — задержка операции в миллисекундах
  - `source` — источник события (bot/scheduler)

### Promtail

**Promtail** собирает логи из Docker контейнеров через Docker JSON log driver и отправляет их в Loki.

**Конфигурация Promtail** (`monitoring/promtail-config.yml`):

1. **Сбор логов:** Promtail читает логи из `/var/lib/docker/containers/*/*-json.log` (стандартный путь Docker JSON logs)

2. **Парсинг:**
   - Парсинг Docker JSON формата (поля `log`, `stream`, `time`)
   - Извлечение JSON из поля `log` (структурированные логи приложения)
   - Парсинг полей `timestamp`, `level`, `message`, `extra`
   - Извлечение вложенных полей из `extra` (service, env, event, status)

3. **Labels (низкая кардинальность):**
   - `service` — имя сервиса (bot/celery-worker/celery-beat)
   - `env` — окружение (production/staging)
   - `level` — уровень логирования (INFO/WARNING/ERROR)

4. **Отправка в Loki:** Логи отправляются в `http://loki:3100/loki/api/v1/push`

### Полезные запросы LogQL

#### 1. Найти все ошибки 5xx для `/generate` за последние 6 часов

```logql
{service="wednesday-bot", level="ERROR"}
  | json
  | message =~ ".*generate.*"
  | extra.status =~ ".*5[0-9]{2}.*"
```

#### 2. Найти логи для конкретного `user_id`

```logql
{service="wednesday-bot"}
  | json
  | extra.user_id = "123456789"
```

#### 3. Найти все ошибки генерации за последний час

```logql
{service="wednesday-bot", level="ERROR"}
  | json
  | extra.event = "generation"
```

#### 4. Найти логи с высокой латентностью (> 30 секунд)

```logql
{service="wednesday-bot"}
  | json
  | extra.latency_ms > 30000
```

#### 5. Найти все healthcheck failures

```logql
{service="wednesday-bot"}
  | json
  | extra.event = "healthcheck_failed"
```

#### 6. Найти логи Celery задач с ошибками

```logql
{service="celery-worker", level="ERROR"}
  | json
  | extra.event =~ ".*celery.*"
```

#### 7. Подсчитать количество генераций по статусу за последний час

```logql
sum by (status) (
  count_over_time(
    {service="wednesday-bot"}
      | json
      | extra.event = "generation"
      | extra.status != ""
      [1h]
  )
)
```

#### 8. Найти логи с retry попытками

```logql
{service="wednesday-bot"}
  | json
  | extra.status = "retry"
```

---

## Алерты (Alerting)

### Основные правила

В Prometheus настроены следующие критические правила алертинга (файл `monitoring/prometheus/rules/metrics-rules.yml`):

#### 1. Celery Queue Overload

**Правило:**
```yaml
- alert: CeleryQueueOverload
  expr: celery_queue_length{queue_name="wednesday"} > 50
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Очередь Celery перегружена"
    description: "Очередь {{ $labels.queue_name }} содержит {{ $value }} задач (порог: 50)"
```

**Когда срабатывает:** Когда длина очереди `wednesday` превышает 50 задач в течение 5 минут.

**Действия:**
- Проверить количество активных Celery workers
- Проверить производительность задач
- Рассмотреть масштабирование workers

#### 2. High Generation Latency

**Правило:**
```yaml
- alert: HighGenerationLatency
  expr: |
    histogram_quantile(0.99,
      sum by (le, service) (rate(frog_generation_latency_seconds_bucket[5m]))
    ) > 45
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Высокая латентность генерации (P99 > 45s)"
    description: "P99 латентности генерации составляет {{ $value }}s (порог: 45s)"
```

**Когда срабатывает:** Когда P99 латентности генерации превышает 45 секунд в течение 10 минут.

**Действия:**
- Проверить доступность Kandinsky API
- Проверить доступность GigaChat API
- Проверить сетевую задержку
- Проверить использование ресурсов (CPU/Memory)

#### 3. Service Down

**Правило:**
```yaml
- alert: ServiceDown
  expr: up{job=~"bot|celery-worker|celery-beat"} == 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Сервис {{ $labels.job }} недоступен"
    description: "Healthcheck endpoint /health недоступен для {{ $labels.job }} в течение 2 минут"
```

**Когда срабатывает:** Когда healthcheck endpoint `/health` возвращает не 200 в течение 2 минут.

**Действия:**
- Проверить статус контейнера: `docker compose ps`
- Проверить логи: `docker compose logs <service>`
- Проверить доступность зависимостей (PostgreSQL, Redis)
- Перезапустить сервис при необходимости

#### 4. Database Connection Error

**Правило:**
```yaml
- alert: DatabaseConnectionError
  expr: |
    increase(
      {service="wednesday-bot", level="ERROR"}
        | json
        | extra.event =~ ".*postgres.*|.*database.*"
        [5m]
    ) > 5
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Частые ошибки подключения к PostgreSQL"
    description: "Обнаружено {{ $value }} ошибок подключения к БД за последние 5 минут"
```

**Когда срабатывает:** Когда в логах появляется более 5 ошибок подключения к PostgreSQL за 5 минут.

**Действия:**
- Проверить статус PostgreSQL: `docker compose ps postgres`
- Проверить логи PostgreSQL: `docker compose logs postgres`
- Проверить доступность сети между контейнерами
- Проверить лимиты подключений в PostgreSQL
- Проверить использование ресурсов PostgreSQL

#### 5. High Generation Error Rate

**Правило:**
```yaml
- alert: HighGenerationErrorRate
  expr: |
    sum(rate(frog_generations_total{status="failure"}[5m])) /
    sum(rate(frog_generations_total[5m])) > 0.05
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Доля ошибок генерации >5%"
    description: "Error rate составляет {{ $value | humanizePercentage }}"
```

**Когда срабатывает:** Когда доля неудачных генераций превышает 5% в течение 5 минут.

**Действия:**
- Проверить доступность Kandinsky API
- Проверить доступность GigaChat API
- Проверить логи на детали ошибок
- Проверить circuit breaker статус

#### 6. Celery Task Failures

**Правило:**
```yaml
- alert: CeleryTaskFailures
  expr: sum(rate(celery_task_failures_total[5m])) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Есть фейлы Celery задач"
    description: "Обнаружены неудачные задачи в Celery"
```

**Когда срабатывает:** Когда есть неудачные Celery задачи в течение 5 минут.

**Действия:**
- Проверить логи Celery worker
- Проверить детали ошибок в метриках `celery_task_failures_total`
- Проверить доступность зависимостей (PostgreSQL, Redis, внешние API)

#### 7. Exporter Down

**Правило:**
```yaml
- alert: ExporterDown
  expr: up == 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Target {{ $labels.job }} недоступен"
    description: "Prometheus не может собрать метрики с {{ $labels.job }}"
```

**Когда срабатывает:** Когда Prometheus не может собрать метрики с target'а в течение 2 минут.

**Действия:**
- Проверить доступность endpoint `/metrics`
- Проверить сетевую связность
- Проверить статус контейнера

### Каналы уведомлений

Алерты могут быть настроены для отправки в следующие каналы через **Alertmanager**:

#### 1. Telegram

**Конфигурация Alertmanager:**
```yaml
receivers:
  - name: telegram
    telegram_configs:
      - bot_token: 'YOUR_BOT_TOKEN'
        chat_id: YOUR_CHAT_ID
        parse_mode: 'HTML'
        message: |
          <b>Alert:</b> {{ .GroupLabels.alertname }}
          <b>Severity:</b> {{ .CommonLabels.severity }}
          <b>Description:</b> {{ .CommonAnnotations.description }}
```

#### 2. Email

**Конфигурация Alertmanager:**
```yaml
receivers:
  - name: email
    email_configs:
      - to: 'admin@example.com'
        from: 'alerts@example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'alerts@example.com'
        auth_password: 'password'
        headers:
          Subject: 'Alert: {{ .GroupLabels.alertname }}'
```

#### 3. PagerDuty

**Конфигурация Alertmanager:**
```yaml
receivers:
  - name: pagerduty
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
        description: '{{ .CommonAnnotations.description }}'
```

#### 4. Webhook (для интеграции с другими системами)

**Конфигурация Alertmanager:**
```yaml
receivers:
  - name: webhook
    webhook_configs:
      - url: 'https://your-webhook-endpoint.com/alerts'
        http_config:
          basic_auth:
            username: 'user'
            password: 'pass'
```

**Рекомендации по настройке:**

- **Critical алерты** → Telegram + Email + PagerDuty (для немедленного реагирования)
- **Warning алерты** → Telegram + Email (для мониторинга)
- **Info алерты** → Email (для информационных целей)

---

## Конфигурация

### Расположение конфигурационных файлов

Все конфигурации мониторинга находятся в директории `monitoring/`:

```
monitoring/
├── prometheus/
│   ├── prometheus.yml          # Основная конфигурация Prometheus
│   └── rules/
│       ├── metrics-rules.yml   # Правила алертов и recording rules
│       └── metrics-rules.test.yml  # Тестовые правила
├── loki-config.yml             # Конфигурация Loki
├── promtail-config.yml         # Конфигурация Promtail
└── grafana/
    └── provisioning/
        ├── datasources/
        │   ├── datasource-prometheus.yml  # Prometheus datasource
        │   └── datasource-loki.yml       # Loki datasource
        ├── dashboards/
        │   ├── dashboard.yml             # Список дашбордов
        │   ├── wednesday-app-metrics.json  # Дашборд метрик приложения
        │   ├── wednesday-celery-metrics.json  # Дашборд метрик Celery
        │   ├── wednesday-retry-metrics.json   # Дашборд метрик retry
        │   └── wednesday-logs-dashboard.json   # Дашборд логов
        └── alerting/
            ├── metrics-rules.yml        # Правила алертов для Grafana
            └── logging-rules.yml        # Правила алертов для логов
```

### Prometheus

**Файл:** `monitoring/prometheus/prometheus.yml`

**Основные настройки:**
- `scrape_interval: 15s` — интервал сбора метрик
- `scrape_timeout: 10s` — таймаут сбора метрик
- `evaluation_interval: 15s` — интервал оценки правил алертов
- `storage.tsdb.retention.time: 15d` — время хранения метрик (15 дней)

**Targets:**
- `bot:8000` — метрики основного бота
- `celery-worker:8000` — метрики Celery worker
- `celery-beat:8000` — метрики Celery beat

**Правила:**
- Recording rules для агрегации метрик (P95, P99, error rates)
- Alert rules для критических событий

### Loki

**Файл:** `monitoring/loki-config.yml`

**Основные настройки:**
- `retention_period: 168h` — время хранения логов (7 дней)
- `ingestion_rate_mb: 4` — лимит скорости приёма логов
- `max_streams_per_user: 50000` — максимальное количество потоков

**Хранение:**
- Использует файловую систему для хранения chunks и индексов
- Пути: `/loki/chunks`, `/loki/index`

### Promtail

**Файл:** `monitoring/promtail-config.yml`

**Основные настройки:**
- `http_listen_port: 9080` — порт для метрик Promtail
- `positions.filename: /promtail/positions.yaml` — файл позиций для отслеживания прогресса

**Pipeline stages:**
1. Парсинг Docker JSON формата
2. Извлечение JSON из поля `log`
3. Парсинг полей `timestamp`, `level`, `message`, `extra`
4. Извлечение labels из `extra` (service, env, level)
5. Установка timestamp из поля `timestamp`

### Grafana

**Datasources:**
- **Prometheus:** `http://prometheus:9090`
- **Loki:** `http://loki:3100`

**Dashboards:**
- Автоматически загружаются из `monitoring/grafana/provisioning/dashboards/`
- Все дашборды в формате JSON

**Доступ:**
- URL: `http://localhost:3000`
- Логин по умолчанию: `admin` / `admin` (рекомендуется изменить при первом входе)

### Переменные окружения

**Для бота:**
- `PROMETHEUS_EXPORTER_PORT=8000` — порт Prometheus exporter
- `HEALTHCHECK_PORT=8080` — порт healthcheck endpoint
- `LOG_TO_FILE=0` — логи в stdout (JSON) для Promtail
- `SERVICE_NAME=wednesday-bot` — имя сервиса для логов

**Для Celery:**
- `SERVICE_NAME=celery-worker` или `SERVICE_NAME=celery-beat` — имя сервиса для логов

### Обновление конфигураций

**Prometheus:**
```bash
# Перезагрузка конфигурации без перезапуска (если включен --web.enable-lifecycle)
curl -X POST http://localhost:9090/-/reload
```

**Loki:**
```bash
# Перезапуск контейнера для применения изменений
docker compose restart loki
```

**Promtail:**
```bash
# Перезапуск контейнера для применения изменений
docker compose restart promtail
```

**Grafana:**
- Дашборды и datasources обновляются автоматически при изменении файлов
- Для применения изменений может потребоваться перезапуск: `docker compose restart grafana`

---

## Дополнительные ресурсы

- [Архитектура проекта](ARCHITECTURE.md)
- [Руководство по развертыванию](DEPLOYMENT.md)
- [Справочник API](API_REFERENCE.md)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Loki Documentation](https://grafana.com/docs/loki/latest/)
- [LogQL Documentation](https://grafana.com/docs/loki/latest/logql/)

---

**Последнее обновление:** 2025-01-15
