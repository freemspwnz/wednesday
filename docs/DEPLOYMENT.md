# Руководство по развертыванию Wednesday Frog Bot

Данное руководство описывает процесс развертывания Telegram-бота "Wednesday Frog Bot" в production среде с использованием Docker Compose.

## Содержание

1. [Требования к инфраструктуре](#infrastructure-requirements)
2. [Продакшен Docker Compose конфигурация](#production-docker-compose-config)
3. [Настройка окружения](#environment-configuration)
4. [Процедура развертывания (Первый запуск)](#deployment-first-run)
5. [Обновление бота (Без downtime)](#zero-downtime-updates)
6. [Backup и Restore](#backup-and-restore)
7. [Troubleshooting](#troubleshooting)

---

## Требования к инфраструктуре {#infrastructure-requirements}

### Минимальные требования к ресурсам

**Рекомендуемые минимальные требования для production:**

- **CPU:** 2 ядра (4 ядра для высокой нагрузки)
- **RAM:** 4 GB (8 GB для высокой нагрузки)
- **Диск:** 20 GB свободного места (SSD рекомендуется)
- **Сеть:** Стабильное интернет-соединение для доступа к Telegram API, Kandinsky API и GigaChat API

**Требования к ресурсам по сервисам:**

| Сервис | CPU | RAM | Диск |
|--------|-----|-----|------|
| PostgreSQL | 0.25-0.75 cores | 256MB-1GB | ~5GB |
| Redis | 0.2-0.5 cores | 128MB-512MB | ~1GB |
| Bot | 0.25-0.5 cores | 256MB-512MB | ~2GB |
| Celery Worker | 0.25-0.5 cores | 256MB-512MB | ~2GB |
| Celery Beat | 0.1-0.3 cores | 128MB-256MB | ~100MB |
| Prometheus | 0.25-0.75 cores | 256MB-1GB | ~5GB |
| Loki | 0.25-0.5 cores | 256MB-512MB | ~2GB |
| Grafana | 0.25-0.5 cores | 256MB-512MB | ~500MB |
| Promtail | 0.1-0.25 cores | 128MB-256MB | ~100MB |

**Итого (с запасом):** ~2 CPU cores, ~4GB RAM, ~20GB диск

### Требуемые сервисы

**Обязательные:**

- **Docker** версии 20.10 или выше
- **Docker Compose** версии 2.0 или выше
- **PostgreSQL Server** версии 14+ (или использование Docker-контейнера из `docker-compose.yml`)
- **Redis Server** версии 6+ (или использование Docker-контейнера из `docker-compose.yml`)

**Опциональные (для мониторинга):**

- Prometheus (включен в конфигурацию)
- Loki (включен в конфигурацию)
- Grafana (включен в конфигурацию)
- Promtail (включен в конфигурацию)

### Проверка установки

```bash
# Проверка Docker
docker --version
# Docker version 20.10.0 или выше

# Проверка Docker Compose
docker compose version
# Docker Compose version v2.0.0 или выше

# Проверка доступных ресурсов
docker system info | grep -E "CPUs|Total Memory"
```

---

## Продакшен Docker Compose конфигурация {#production-docker-compose-config}

### Файл `docker-compose.yml`

Создайте файл `docker-compose.yml` в корне проекта:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: wednesday_postgres_prod
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      POSTGRES_DB: ${POSTGRES_DB}
    expose:
      - "5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    secrets:
      - postgres_password
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 2g
        reservations:
          cpus: "0.5"
          memory: 512m
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  redis:
    image: redis:7-alpine
    container_name: wednesday_redis_prod
    restart: unless-stopped
    command: >
      sh -c '
      REDIS_PASSWORD="$(cat /run/secrets/redis_password)";
      redis-server --appendonly yes --appendfsync everysec --requirepass "$$REDIS_PASSWORD"
      '
    expose:
      - "6379"
    volumes:
      - redis_data:/data
    networks:
      - backend
    healthcheck:
      test: >
        sh -c '
        REDIS_PASSWORD="$(cat /run/secrets/redis_password)";
        redis-cli -a "$$REDIS_PASSWORD" ping
        '
      interval: 10s
      timeout: 5s
      retries: 5
    secrets:
      - redis_password
    deploy:
      resources:
        limits:
          cpus: "0.75"
          memory: 1g
        reservations:
          cpus: "0.25"
          memory: 256m
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  bot-init:
    image: wednesday-bot:prod
    container_name: wednesday_bot_init_prod
    restart: "no"
    user: "0:0"
    volumes:
      - frog_images:/app/data/frogs
      - prompt_storage:/app/data/prompts
      - beat_data:/app/data/beat
    command: ["/bin/sh", "-lc", "mkdir -p /app/data/frogs /app/data/prompts /app/data/beat && chown -R app:app /app/data/frogs /app/data/prompts /app/data/beat"]
    networks:
      - backend
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 256m

  bot:
    image: wednesday-bot:prod
    container_name: wednesday_bot_prod
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp
      - /var/tmp
      - /root/.cache
      - /run
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      bot-init:
        condition: service_completed_successfully
    env_file:
      - .env
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      REDIS_HOST: redis
      REDIS_PASSWORD_FILE: /run/secrets/redis_password
      IMAGE_MODEL_BACKEND: ${IMAGE_MODEL_BACKEND:-kandinsky}
      TEXT_MODEL_BACKEND: ${TEXT_MODEL_BACKEND:-gigachat}
      PROMETHEUS_EXPORTER_PORT: ${PROMETHEUS_EXPORTER_PORT:-8000}
      HEALTHCHECK_PORT: ${HEALTHCHECK_PORT:-8080}
      LOG_TO_FILE: ${LOG_TO_FILE:-0}
      PYTHONDONTWRITEBYTECODE: "1"
      SERVICE_NAME: wednesday-bot
      ENV: production
    volumes:
      - frog_images:/app/data/frogs
      - prompt_storage:/app/data/prompts
    networks:
      - backend
      - monitoring
    expose:
      - "${PROMETHEUS_EXPORTER_PORT:-8000}"
      - "${HEALTHCHECK_PORT:-8080}"
    healthcheck:
      test: ["CMD-SHELL", "python3 -c 'import os, urllib.request, sys; port=os.getenv(\"HEALTHCHECK_PORT\",\"8080\"); resp=urllib.request.urlopen(f\"http://127.0.0.1:{port}/health\"); sys.exit(0 if resp.getcode()==200 else 1)'"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 60s
    secrets:
      - postgres_password
      - redis_password
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1g
        reservations:
          cpus: "0.5"
          memory: 512m
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  celery-worker:
    image: wednesday-bot:prod
    container_name: wednesday_celery_worker_prod
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp
      - /var/tmp
      - /root/.cache
      - /run
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      bot-init:
        condition: service_completed_successfully
    env_file:
      - .env
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      REDIS_HOST: redis
      REDIS_PASSWORD_FILE: /run/secrets/redis_password
      TZ: ${SCHEDULER_TZ:-Europe/Amsterdam}
      IMAGE_MODEL_BACKEND: ${IMAGE_MODEL_BACKEND:-kandinsky}
      TEXT_MODEL_BACKEND: ${TEXT_MODEL_BACKEND:-gigachat}
      LOG_TO_FILE: ${LOG_TO_FILE:-0}
      PYTHONDONTWRITEBYTECODE: "1"
      SERVICE_NAME: celery-worker
      ENV: production
    command: celery -A services.celery_app worker --pool=threads --loglevel=info --concurrency=8 -Q wednesday,images,maintenance
    volumes:
      - frog_images:/app/data/frogs
      - prompt_storage:/app/data/prompts
    networks:
      - backend
      - monitoring
    healthcheck:
      test: ["CMD-SHELL", "celery -A services.celery_app inspect ping --timeout=2 >/dev/null 2>&1 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    secrets:
      - postgres_password
      - redis_password
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1g
        reservations:
          cpus: "0.5"
          memory: 512m
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  celery-beat:
    image: wednesday-bot:prod
    container_name: wednesday_celery_beat_prod
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp
      - /var/tmp
      - /root/.cache
      - /run
      - /celerybeat-schedule
    depends_on:
      redis:
        condition: service_healthy
      bot-init:
        condition: service_completed_successfully
    env_file:
      - .env
    environment:
      REDIS_HOST: redis
      REDIS_PASSWORD_FILE: /run/secrets/redis_password
      TZ: ${SCHEDULER_TZ:-Europe/Amsterdam}
      LOG_TO_FILE: ${LOG_TO_FILE:-0}
      PYTHONDONTWRITEBYTECODE: "1"
      SERVICE_NAME: celery-beat
      ENV: production
    command: celery -A services.celery_app beat --loglevel=info
    volumes:
      - beat_data:/app/data/beat
    networks:
      - backend
      - monitoring
    healthcheck:
      test: ["CMD-SHELL", "python3 -c 'import os, time; path=\"/tmp/beat-hb\"; exit(0 if os.path.exists(path) and time.time()-os.path.getmtime(path)<60 else 1)'"]
      interval: 30s
      timeout: 5s
      start_period: 60s
      retries: 3
    secrets:
      - redis_password
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512m
        reservations:
          cpus: "0.25"
          memory: 256m
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  prometheus:
    image: prom/prometheus:v2.54.1
    container_name: wednesday_prometheus_prod
    restart: unless-stopped
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --storage.tsdb.retention.time=15d
      - --web.enable-lifecycle
    volumes:
      - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/prometheus/rules:/etc/prometheus/rules:ro
      - prometheus_data:/prometheus
    expose:
      - "9090"
    networks:
      - backend
      - monitoring
    healthcheck:
      test: ["CMD", "wget", "-q", "-O-", "http://localhost:9090/-/healthy"]
      interval: 30s
      timeout: 5s
      retries: 3
    depends_on:
      - bot
      - celery-worker
      - celery-beat
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 2g
        reservations:
          cpus: "0.5"
          memory: 512m

volumes:
  postgres_data:
  redis_data:
  frog_images:
  prompt_storage:
  beat_data:
  prometheus_data:

networks:
  backend:
    driver: bridge
  monitoring:
    driver: bridge

secrets:
  postgres_password:
    file: ./secrets/postgres_password
  redis_password:
    file: ./secrets/redis_password
```

### Важные замечания

1. **Celery Workers и Celery Beat используют один и тот же образ** (`wednesday-bot:prod`), но запускаются с разными командами:
   - `celery-worker`: `celery -A services.celery_app worker --pool=threads --loglevel=info --concurrency=8 -Q wednesday,images,maintenance`
   - `celery-beat`: `celery -A services.celery_app beat --loglevel=info`

2. **Volumes для персистентных данных:**
   - `postgres_data` — данные PostgreSQL
   - `redis_data` — данные Redis (AOF persistence)
   - `frog_images` — сгенерированные изображения жабы
   - `prompt_storage` — файловое хранилище промптов GigaChat
   - `beat_data` — состояние расписания Celery Beat

3. **Prometheus Exporter** настроен на порту `8000` (по умолчанию) и доступен через внутреннюю сеть `monitoring`.

---

## Настройка окружения {#environment-configuration}

### Файл `.env`

Создайте файл `.env` в корне проекта на основе `env_example.txt`:

```bash
cp env_example.txt .env
```

### Критические переменные окружения

#### Обязательные переменные

```bash
# Telegram Bot Token (получите у @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Kandinsky API (получите на https://fusionbrain.ai)
KANDINSKY_API_KEY=your_kandinsky_api_key_here
KANDINSKY_SECRET_KEY=your_kandinsky_secret_key_here

# ID чата для отправки сообщений
CHAT_ID=your_chat_or_channel_id_here

# ID администратора (получите от @userinfobot)
ADMIN_CHAT_ID=your_admin_chat_id_here

# PostgreSQL настройки
POSTGRES_USER=wednesday_user
POSTGRES_DB=wednesday_db
POSTGRES_HOST=postgres  # Имя сервиса в docker-compose

# Redis настройки (для работы внутри Docker сети)
REDIS_HOST=redis  # Имя сервиса в docker-compose
REDIS_PORT=6379
REDIS_DB=0

# GigaChat (опционально, для генерации промптов)
GIGACHAT_AUTHORIZATION_KEY=your_gigachat_key_here

# Планировщик
SCHEDULER_SEND_TIMES=09:00,12:00,18:00
SCHEDULER_TZ=Europe/Amsterdam
SCHEDULER_WEDNESDAY_DAY=2

# Окружение
ENV=production
LOG_LEVEL=INFO
```

#### Опциональные переменные

```bash
# Prometheus Exporter
PROMETHEUS_EXPORTER_PORT=8000

# Healthcheck
HEALTHCHECK_PORT=8080

# Логирование
LOG_TO_FILE=0  # 0 = только stdout (рекомендуется для Docker)

# Retry настройки
RETRY_MAX_ATTEMPTS=5
RETRY_MULTIPLIER=1.0
RETRY_MIN_WAIT=2.0
RETRY_MAX_WAIT=30.0

# Sentry (опционально)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production
RELEASE=v1.0.0
```

### Управление секретами

**⚠️ ВАЖНО: Безопасность секретов**

В production среде **НИКОГДА** не храните секреты в `.env` файле, который может быть закоммичен в Git. Используйте один из следующих подходов:

#### Вариант 1: Docker Secrets (рекомендуется)

Секреты хранятся в файлах в директории `secrets/`:

```bash
# Создайте директорию secrets (если не существует)
mkdir -p secrets

# Установите права доступа
chmod 700 secrets

# Создайте файлы с секретами
echo "your_postgres_password" > secrets/postgres_password
echo "your_redis_password" > secrets/redis_password

# Установите права доступа на файлы
chmod 600 secrets/postgres_password
chmod 600 secrets/redis_password
```

В `docker-compose.yml` секреты подключаются через секцию `secrets`:

```yaml
secrets:
  postgres_password:
    file: ./secrets/postgres_password
  redis_password:
    file: ./secrets/redis_password
```

#### Вариант 2: Переменные окружения хоста

Установите секреты как переменные окружения на хосте перед запуском:

```bash
export POSTGRES_PASSWORD="your_postgres_password"
export REDIS_PASSWORD="your_redis_password"
docker compose -f docker-compose.yml up -d
```

#### Вариант 3: HashiCorp Vault или AWS Secrets Manager

Для enterprise-окружений рекомендуется использовать специализированные системы управления секретами:

- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- Google Secret Manager

Интеграция с этими системами требует дополнительной настройки и выходит за рамки данного руководства.

### Проверка конфигурации

Перед запуском убедитесь, что все обязательные переменные установлены:

```bash
# Проверка наличия обязательных переменных
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
required = ['TELEGRAM_BOT_TOKEN', 'KANDINSKY_API_KEY', 'KANDINSKY_SECRET_KEY',
            'CHAT_ID', 'ADMIN_CHAT_ID', 'POSTGRES_USER', 'POSTGRES_DB']
missing = [v for v in required if not os.getenv(v)]
if missing:
    print(f'Отсутствуют переменные: {missing}')
    exit(1)
print('Все обязательные переменные установлены')
"
```

---

## Процедура развертывания (Первый запуск) {#deployment-first-run}

### Шаг 1: Клонирование репозитория

```bash
git clone https://github.com/your-username/wednesday-tg-bot.git
cd wednesday-tg-bot
```

### Шаг 2: Настройка окружения

```bash
# Создайте файл .env
cp env_example.txt .env
nano .env  # или используйте ваш любимый редактор

# Создайте файлы с секретами
mkdir -p secrets
chmod 700 secrets
echo "your_secure_postgres_password" > secrets/postgres_password
echo "your_secure_redis_password" > secrets/redis_password
chmod 600 secrets/postgres_password
chmod 600 secrets/redis_password
```

### Шаг 3: Сборка Docker-образа

```bash
# Соберите production образ
docker build -t wednesday-bot:prod .

# Проверьте, что образ создан
docker images | grep wednesday-bot
```

### Шаг 4: Запуск инфраструктуры (PostgreSQL и Redis)

```bash
# Запустите только PostgreSQL и Redis
docker compose -f docker-compose.yml up -d postgres redis

# Дождитесь готовности сервисов (проверка healthcheck)
docker compose -f docker-compose.yml ps
```

### Шаг 5: Миграция базы данных

Выполните миграции через унифицированную команду:

```bash
# Запустите миграции через унифицированную команду
make migrate
```

**Примечание:** Функция `ensure_schema()` идемпотентна и безопасна для повторного запуска. Она создаст только отсутствующие таблицы/индексы.

<details>
<summary><strong>Альтернативный способ (не рекомендуется)</strong></summary>

Если по каким-то причинам команда `make migrate` недоступна, можно выполнить миграции через docker-compose:

Добавьте в `docker-compose.yml` временный сервис для миграций:

```yaml
  migrate:
    image: wednesday-bot:prod
    container_name: wednesday_migrate_prod
    restart: "no"
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - .env
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    command: python3 -m utils.postgres_schema
    secrets:
      - postgres_password
    networks:
      - backend
```

Затем выполните:

```bash
docker compose -f docker-compose.yml up migrate
docker compose -f docker-compose.yml rm -f migrate
```

**⚠️ Рекомендуется использовать `make migrate` для консистентности и простоты.**

</details>

**Проверка миграций:**

```bash
# Подключитесь к PostgreSQL и проверьте наличие таблиц
docker compose -f docker-compose.yml exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "\dt"
```

Должны быть созданы следующие таблицы:
- `chats`
- `admins`
- `usage_stats`
- `usage_settings`
- `dispatch_registry`
- `metrics`
- `models_kandinsky`
- `models_gigachat`
- `prompts`
- `images`
- `metrics_events`

### Шаг 6: Запуск всех сервисов

```bash
# Запустите все сервисы
docker compose -f docker-compose.yml up -d

# Проверьте статус всех контейнеров
docker compose -f docker-compose.yml ps

# Просмотрите логи
docker compose -f docker-compose.yml logs -f bot
```

### Шаг 7: Проверка работоспособности

```bash
# Проверка healthcheck бота
docker compose -f docker-compose.yml exec bot python3 -c "
import urllib.request
resp = urllib.request.urlopen('http://127.0.0.1:8080/health')
print(f'Healthcheck status: {resp.getcode()}')
"

# Проверка метрик Prometheus
curl http://localhost:8000/metrics  # Если порт проброшен наружу

# Проверка логов
docker compose -f docker-compose.yml logs --tail=50 bot celery-worker celery-beat
```

---

## Обновление бота (Без downtime) {#zero-downtime-updates}

### Шаг 1: Получение обновлений

```bash
# Перейдите в директорию проекта
cd /path/to/wednesday-tg-bot

# Получите последние изменения
git pull origin main  # или master, в зависимости от вашей ветки

# Проверьте изменения
git log --oneline -5
```

### Шаг 2: Сборка нового образа

```bash
# Соберите новый образ с тегом prod
docker build -t wednesday-bot:prod .

# Проверьте размер образа
docker images wednesday-bot:prod
```

### Шаг 3: Обновление миграций (если необходимо)

Если в обновлении есть изменения схемы БД:

```bash
# Запустите миграции через унифицированную команду
make migrate
```

**Примечание:** Функция `ensure_schema()` идемпотентна и безопасна для повторного запуска. Она создаст только отсутствующие таблицы/индексы.

### Шаг 4: Перезапуск сервисов без downtime

**Стратегия: Rolling update с масштабированием**

```bash
# 1. Масштабируем worker до 0 (останавливаем обработку новых задач)
docker compose -f docker-compose.yml up -d --scale celery-worker=0

# 2. Дождитесь завершения текущих задач (опционально, если нужно)
# Проверьте активные задачи:
docker compose -f docker-compose.yml exec celery-worker celery -A services.celery_app inspect active

# 3. Обновляем и перезапускаем сервисы (без зависимостей, чтобы не трогать postgres/redis)
docker compose -f docker-compose.yml up -d --no-deps bot celery-beat

# 4. Восстанавливаем worker с новым образом
docker compose -f docker-compose.yml up -d --no-deps celery-worker

# 5. Проверяем статус
docker compose -f docker-compose.yml ps
```

**Альтернативная стратегия: Простой перезапуск (с кратковременным downtime)**

Если кратковременный downtime допустим:

```bash
# Остановите только сервисы приложения (не трогая postgres/redis)
docker compose -f docker-compose.yml stop bot celery-worker celery-beat

# Запустите с новым образом
docker compose -f docker-compose.yml up -d bot celery-worker celery-beat

# Проверьте статус
docker compose -f docker-compose.yml ps
```

### Шаг 5: Проверка после обновления

```bash
# Проверка логов
docker compose -f docker-compose.yml logs --tail=100 bot
docker compose -f docker-compose.yml logs --tail=100 celery-worker
docker compose -f docker-compose.yml logs --tail=100 celery-beat

# Проверка healthcheck
docker compose -f docker-compose.yml exec bot python3 -c "
import urllib.request
resp = urllib.request.urlopen('http://127.0.0.1:8080/health')
print(f'Healthcheck: {resp.getcode()}')
"

# Проверка метрик
curl http://localhost:8000/metrics | grep -i "wednesday\|celery" | head -20
```

### Шаг 6: Откат (если необходимо)

Если после обновления возникли проблемы:

```bash
# Откатитесь к предыдущему образу (если сохранили тег)
docker tag wednesday-bot:prod wednesday-bot:prod-backup  # Сделайте бэкап текущего
docker tag wednesday-bot:previous-version wednesday-bot:prod  # Используйте предыдущую версию

# Перезапустите сервисы
docker compose -f docker-compose.yml up -d --no-deps bot celery-worker celery-beat
```

---

## Backup и Restore {#backup-and-restore}

### Backup PostgreSQL

#### Создание дампа

```bash
# Создайте дамп базы данных
docker compose -f docker-compose.yml exec postgres pg_dump \
  -U ${POSTGRES_USER} \
  -d ${POSTGRES_DB} \
  -F c \
  -f /tmp/wednesday_backup_$(date +%Y%m%d_%H%M%S).dump

# Скопируйте дамп на хост
docker compose -f docker-compose.yml cp \
  postgres:/tmp/wednesday_backup_$(date +%Y%m%d_%H%M%S).dump \
  ./backups/
```

**Автоматизированный скрипт для backup:**

```bash
#!/bin/bash
# backup_postgres.sh

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/wednesday_postgres_${DATE}.dump"

mkdir -p "${BACKUP_DIR}"

docker compose -f docker-compose.yml exec -T postgres pg_dump \
  -U ${POSTGRES_USER} \
  -d ${POSTGRES_DB} \
  -F c > "${BACKUP_FILE}"

# Сжатие (опционально)
gzip "${BACKUP_FILE}"

echo "Backup создан: ${BACKUP_FILE}.gz"

# Удаление старых бэкапов (старше 30 дней)
find "${BACKUP_DIR}" -name "wednesday_postgres_*.dump.gz" -mtime +30 -delete
```

#### Восстановление из дампа

```bash
# Остановите бота (чтобы не было активных соединений)
docker compose -f docker-compose.yml stop bot celery-worker celery-beat

# Восстановите дамп
docker compose -f docker-compose.yml exec -T postgres pg_restore \
  -U ${POSTGRES_USER} \
  -d ${POSTGRES_DB} \
  -c \
  < ./backups/wednesday_postgres_20240101_120000.dump

# Запустите бота
docker compose -f docker-compose.yml up -d bot celery-worker celery-beat
```

### Backup Docker Volumes

#### Архивация volumes

```bash
# Backup frog_images
docker run --rm \
  -v wednesday_tg_bot_frog_images:/data:ro \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/frog_images_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Backup prompt_storage
docker run --rm \
  -v wednesday_tg_bot_prompt_storage:/data:ro \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/prompt_storage_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Backup beat_data
docker run --rm \
  -v wednesday_tg_bot_beat_data:/data:ro \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/beat_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
```

**Автоматизированный скрипт:**

```bash
#!/bin/bash
# backup_volumes.sh

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "${BACKUP_DIR}"

VOLUMES=("wednesday_tg_bot_frog_images" "wednesday_tg_bot_prompt_storage" "wednesday_tg_bot_beat_data")

for VOLUME in "${VOLUMES[@]}"; do
  VOLUME_NAME=$(echo "${VOLUME}" | sed 's/wednesday_tg_bot_//')
  BACKUP_FILE="${BACKUP_DIR}/${VOLUME_NAME}_${DATE}.tar.gz"

  docker run --rm \
    -v "${VOLUME}:/data:ro" \
    -v "$(pwd)/${BACKUP_DIR}:/backup" \
    alpine tar czf "/backup/$(basename ${BACKUP_FILE})" -C /data .

  echo "Backup создан: ${BACKUP_FILE}"
done

# Удаление старых бэкапов (старше 30 дней)
find "${BACKUP_DIR}" -name "*_*.tar.gz" -mtime +30 -delete
```

#### Восстановление volumes

```bash
# Восстановление frog_images
docker run --rm \
  -v wednesday_tg_bot_frog_images:/data \
  -v $(pwd)/backups:/backup \
  alpine sh -c "cd /data && rm -rf * && tar xzf /backup/frog_images_20240101_120000.tar.gz"

# Аналогично для других volumes
```

### Полный backup (PostgreSQL + Volumes)

```bash
#!/bin/bash
# full_backup.sh

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT="${BACKUP_DIR}/full_backup_${DATE}"

mkdir -p "${BACKUP_ROOT}"

# 1. Backup PostgreSQL
echo "Создание дампа PostgreSQL..."
docker compose -f docker-compose.yml exec -T postgres pg_dump \
  -U ${POSTGRES_USER} \
  -d ${POSTGRES_DB} \
  -F c > "${BACKUP_ROOT}/postgres.dump"

# 2. Backup Volumes
echo "Архивация volumes..."
for VOLUME in "wednesday_tg_bot_frog_images" "wednesday_tg_bot_prompt_storage" "wednesday_tg_bot_beat_data"; do
  VOLUME_NAME=$(echo "${VOLUME}" | sed 's/wednesday_tg_bot_//')
  docker run --rm \
    -v "${VOLUME}:/data:ro" \
    -v "$(pwd)/${BACKUP_ROOT}:/backup" \
    alpine tar czf "/backup/${VOLUME_NAME}.tar.gz" -C /data .
done

# 3. Создание архива всего backup
cd "${BACKUP_DIR}"
tar czf "full_backup_${DATE}.tar.gz" "full_backup_${DATE}"
rm -rf "full_backup_${DATE}"

echo "Полный backup создан: ${BACKUP_DIR}/full_backup_${DATE}.tar.gz"
```

### Планирование автоматических backup

Добавьте в crontab:

```bash
# Ежедневный backup в 2:00 ночи
0 2 * * * /path/to/wednesday-tg-bot/scripts/full_backup.sh >> /var/log/wednesday_backup.log 2>&1
```

---

## Troubleshooting {#troubleshooting}

### Проблема: Бот не отвечает

**Симптомы:**
- Бот не реагирует на команды в Telegram
- Healthcheck возвращает ошибку

**Диагностика:**

```bash
# 1. Проверьте логи бота
docker compose -f docker-compose.yml logs --tail=100 bot

# 2. Проверьте логи worker (если команды обрабатываются через Celery)
docker compose -f docker-compose.yml logs --tail=100 celery-worker

# 3. Проверьте статус контейнеров
docker compose -f docker-compose.yml ps

# 4. Проверьте healthcheck
docker compose -f docker-compose.yml exec bot python3 -c "
import urllib.request
try:
    resp = urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)
    print(f'Healthcheck OK: {resp.getcode()}')
except Exception as e:
    print(f'Healthcheck FAILED: {e}')
"

# 5. Проверьте подключение к Telegram API
docker compose -f docker-compose.yml exec bot python3 -c "
from telegram import Bot
import asyncio
async def test():
    bot = Bot(token='${TELEGRAM_BOT_TOKEN}')
    me = await bot.get_me()
    print(f'Bot connected: {me.username}')
asyncio.run(test())
"
```

**Возможные решения:**

1. **Проблема с токеном Telegram:**
   - Проверьте правильность `TELEGRAM_BOT_TOKEN` в `.env`
   - Убедитесь, что бот не был удален в @BotFather

2. **Проблема с сетью:**
   - Проверьте доступность интернета из контейнера: `docker compose -f docker-compose.yml exec bot ping -c 3 8.8.8.8`
   - Проверьте настройки прокси (если используются)

3. **Проблема с базой данных:**
   - Проверьте подключение к PostgreSQL: `docker compose -f docker-compose.yml exec bot python3 -m utils.postgres_client`
   - Проверьте логи PostgreSQL: `docker compose -f docker-compose.yml logs postgres`

4. **Перезапуск бота:**
   ```bash
   docker compose -f docker-compose.yml restart bot
   ```

### Проблема: Celery не запускается

**Симптомы:**
- `celery-worker` или `celery-beat` контейнеры падают или не запускаются
- В логах ошибки подключения к Redis

**Диагностика:**

```bash
# 1. Проверьте логи worker
docker compose -f docker-compose.yml logs --tail=100 celery-worker

# 2. Проверьте логи beat
docker compose -f docker-compose.yml logs --tail=100 celery-beat

# 3. Проверьте подключение к Redis
docker compose -f docker-compose.yml exec celery-worker python3 -c "
import redis
r = redis.Redis(host='redis', port=6379, db=0, password='${REDIS_PASSWORD}')
r.ping()
print('Redis connection OK')
"

# 4. Проверьте статус Redis
docker compose -f docker-compose.yml exec redis redis-cli -a '${REDIS_PASSWORD}' ping
```

**Возможные решения:**

1. **Проблема с подключением к Redis:**
   - Проверьте, что Redis запущен: `docker compose -f docker-compose.yml ps redis`
   - Проверьте правильность `REDIS_PASSWORD` в секретах
   - Проверьте сеть: `docker compose -f docker-compose.yml exec celery-worker ping -c 3 redis`

2. **Проблема с паролем Redis:**
   - Убедитесь, что файл `secrets/redis_password` существует и содержит правильный пароль
   - Проверьте права доступа: `ls -la secrets/redis_password`

3. **Перезапуск Celery сервисов:**
   ```bash
   docker compose -f docker-compose.yml restart celery-worker celery-beat
   ```

### Проблема: Ошибки миграции

**Симптомы:**
- Ошибки при выполнении `ensure_schema()`
- Таблицы не создаются в PostgreSQL

**Диагностика:**

```bash
# 1. Проверьте версию PostgreSQL
docker compose -f docker-compose.yml exec postgres psql --version

# 2. Проверьте подключение к БД
docker compose -f docker-compose.yml exec bot python3 -c "
import asyncio
from utils.postgres_client import init_postgres_pool, get_postgres_pool, close_postgres_pool

async def test():
    await init_postgres_pool()
    pool = get_postgres_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval('SELECT version()')
        print(f'PostgreSQL version: {result}')
    await close_postgres_pool()

asyncio.run(test())
"

# 3. Проверьте существующие таблицы
docker compose -f docker-compose.yml exec postgres psql \
  -U ${POSTGRES_USER} \
  -d ${POSTGRES_DB} \
  -c "\dt"

# 4. Попробуйте запустить миграции вручную
make migrate
```

**Возможные решения:**

1. **Несовместимая версия PostgreSQL:**
   - Убедитесь, что используется PostgreSQL 14+ (в `docker-compose.yml` указан `postgres:16-alpine`)
   - Проверьте логи PostgreSQL на ошибки: `docker compose -f docker-compose.yml logs postgres`

2. **Проблемы с правами доступа:**
   - Проверьте, что пользователь PostgreSQL имеет права на создание таблиц
   - Проверьте правильность `POSTGRES_USER` и `POSTGRES_PASSWORD`

3. **Конфликты схемы:**
   - Если таблицы уже существуют, `ensure_schema()` должна быть идемпотентной
   - При необходимости удалите проблемные таблицы вручную и запустите миграции заново

4. **Проблемы с подключением:**
   - Проверьте, что PostgreSQL доступен из контейнера бота: `docker compose -f docker-compose.yml exec bot ping -c 3 postgres`
   - Проверьте переменные окружения: `docker compose -f docker-compose.yml exec bot env | grep POSTGRES`

### Проблема: Высокое использование ресурсов

**Симптомы:**
- Контейнеры потребляют много CPU/RAM
- Медленная работа бота

**Диагностика:**

```bash
# 1. Проверьте использование ресурсов
docker stats

# 2. Проверьте метрики Prometheus
curl http://localhost:8000/metrics | grep -E "cpu|memory|process"

# 3. Проверьте количество активных задач Celery
docker compose -f docker-compose.yml exec celery-worker \
  celery -A services.celery_app inspect active
```

**Возможные решения:**

1. **Увеличьте лимиты ресурсов в `docker-compose.yml`:**
   ```yaml
   deploy:
     resources:
       limits:
         cpus: "2.0"  # Увеличьте при необходимости
         memory: 2g
   ```

2. **Оптимизируйте concurrency Celery worker:**
   - Уменьшите `--concurrency` в команде worker, если CPU перегружен
   - Увеличьте, если есть задержки в обработке задач

3. **Проверьте утечки памяти:**
   - Перезапускайте контейнеры периодически
   - Используйте мониторинг для отслеживания использования памяти

### Проблема: Проблемы с генерацией изображений

**Симптомы:**
- Ошибки при выполнении команды `/frog`
- Таймауты при генерации изображений

**Диагностика:**

```bash
# 1. Проверьте логи worker (генерация происходит в Celery)
docker compose -f docker-compose.yml logs --tail=100 celery-worker | grep -i "kandinsky\|error"

# 2. Проверьте доступность Kandinsky API
docker compose -f docker-compose.yml exec bot python3 -c "
import requests
resp = requests.get('https://fusionbrain.ai', timeout=10)
print(f'Kandinsky API доступен: {resp.status_code}')
"

# 3. Проверьте API ключи
docker compose -f docker-compose.yml exec bot python3 -c "
from utils.config import config
print(f'Kandinsky API Key установлен: {bool(config.kandinsky_api_key)}')
"
```

**Возможные решения:**

1. **Проблемы с API ключами:**
   - Проверьте правильность `KANDINSKY_API_KEY` и `KANDINSKY_SECRET_KEY`
   - Убедитесь, что ключи не истекли

2. **Проблемы с сетью:**
   - Проверьте доступность `fusionbrain.ai` из контейнера
   - Проверьте настройки прокси (если используются)

3. **Увеличьте таймауты:**
   - Установите `GENERATION_TIMEOUT=120` в `.env` для долгих генераций

### Дополнительные команды для диагностики

```bash
# Просмотр всех логов
docker compose -f docker-compose.yml logs --tail=200

# Просмотр логов конкретного сервиса
docker compose -f docker-compose.yml logs -f bot

# Проверка сетевых подключений
docker compose -f docker-compose.yml exec bot netstat -tuln

# Проверка использования диска volumes
docker system df -v

# Очистка неиспользуемых ресурсов (осторожно!)
docker system prune -a --volumes
```

---

## Дополнительные ресурсы

- [Архитектура проекта](ARCHITECTURE.md)
- [Руководство по установке](INSTALLATION.md)
- [Руководство по тестированию](tests/README.md)
- [Changelog](CHANGELOG.md)

---

**Последнее обновление:** 2025-12-15
