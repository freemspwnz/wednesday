# Инструкция по установке Wednesday Frog Bot 🐸

Быстрое руководство по локальному запуску проекта для разработки с использованием Docker Compose.

## Содержание

1. [Требования](#требования)
2. [Шаг 1: Клонирование и Конфигурация](#шаг-1-клонирование-и-конфигурация)
3. [Шаг 2: Сборка и Запуск](#шаг-2-сборка-и-запуск)
4. [Шаг 3: Миграция Базы Данных (Первый Запуск)](#шаг-3-миграция-базы-данных-первый-запуск)
5. [Шаг 4: Тестирование](#шаг-4-тестирование)
6. [Дальнейшие шаги](#дальнейшие-шаги)

## Требования

Для локальной разработки вам понадобятся:

- **Docker** (версия 20.10+)
- **Docker Compose** (версия 2.0+)
- **Python 3.10+** (для локальных скриптов и утилит)
- **Git** (для клонирования репозитория)

### Проверка установки

```bash
# Проверка Docker
docker --version

# Проверка Docker Compose
docker compose version

# Проверка Python (опционально, для локальных скриптов)
python3 --version
```

## Шаг 1: Клонирование и Конфигурация

### 1.1. Клонирование репозитория

```bash
git clone https://github.com/your-username/wednesday-tg-bot.git
cd wednesday-tg-bot
```

### 1.2. Создание файла конфигурации

Скопируйте пример конфигурации:

```bash
cp env_example.txt .env
```

### 1.3. Настройка переменных окружения

Откройте файл `.env` и заполните **минимально необходимые** переменные:

```env
# === ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ===

# Токен Telegram бота (получите у @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# API ключи Kandinsky (получите на https://fusionbrain.ai)
KANDINSKY_API_KEY=your_kandinsky_api_key_here
KANDINSKY_SECRET_KEY=your_kandinsky_secret_key_here

# ID чата для отправки сообщений
CHAT_ID=your_chat_id_here

# === НАСТРОЙКИ POSTGRES ===

# Имя пользователя PostgreSQL
POSTGRES_USER=wednesday_user

# Пароль пользователя PostgreSQL
POSTGRES_PASSWORD=your_secure_password_here

# Имя базы данных
POSTGRES_DB=wednesdaydb

# Хост PostgreSQL (для docker-compose используйте 'postgres')
POSTGRES_HOST=postgres

# Порт PostgreSQL
POSTGRES_PORT=5432

# === НАСТРОЙКИ REDIS ===

# Хост Redis (для docker-compose используйте 'redis')
REDIS_HOST=redis

# Порт Redis
REDIS_PORT=6379

# Пароль Redis (опционально, но рекомендуется)
REDIS_PASSWORD=your_redis_password_here
```

**Примечание:** Полный список доступных переменных и их описание см. в файле `env_example.txt`.

### 1.4. Создание файлов secrets

Docker Compose использует secrets для безопасного хранения паролей. Создайте директорию и файлы:

```bash
mkdir -p secrets

# Создайте файл с паролем PostgreSQL
echo "your_secure_postgres_password_here" > secrets/postgres_password

# Создайте файл с паролем Redis
echo "your_secure_redis_password_here" > secrets/redis_password

# Создайте файл с паролем Grafana (опционально, для мониторинга)
echo "admin" > secrets/grafana_admin_password

# Установите безопасные права доступа
chmod 600 secrets/postgres_password secrets/redis_password secrets/grafana_admin_password
```

**Важно:** Убедитесь, что пароли в `secrets/*` совпадают с паролями в `.env` (или используйте одинаковые значения для упрощения).

## Шаг 2: Сборка и Запуск

### 2.1. Сборка и запуск всех сервисов

Основная команда для сборки Docker-образов и запуска всех сервисов:

```bash
docker compose -f docker-compose.yml up -d --build
```

Эта команда:
- Соберёт Docker-образ бота (`wednesday-bot:local`)
- Запустит все необходимые сервисы в фоновом режиме (`-d`)
- Создаст и подключит необходимые Docker volumes

### 2.2. Запущенные сервисы

После выполнения команды будут запущены следующие сервисы:

- **`postgres`** — PostgreSQL 16 для хранения всех персистентных данных (чаты, метрики, админы, модели, реестр рассылок)
- **`redis`** — Redis 7 для кэша, rate limiter'а, circuit breaker'а и временного состояния
- **`bot`** — Wednesday Frog Bot (основной сервис)
- **`celery_worker`** — Celery worker для выполнения фоновых задач (генерация изображений, отправка сообщений)
- **`celery_beat`** — Celery beat для планирования периодических задач (отправка по средам)

**Опциональные сервисы мониторинга** (также запускаются автоматически):
- **`loki`** — Система сбора логов
- **`grafana`** — Дашборды и визуализация (доступна на http://localhost:3000)
- **`prometheus`** — Сбор метрик
- **`promtail`** — Агент для отправки логов в Loki

### 2.3. Проверка статуса сервисов

```bash
# Просмотр статуса всех сервисов
docker compose ps

# Просмотр логов бота в реальном времени
docker compose logs -f bot

# Просмотр логов всех сервисов
docker compose logs -f
```

### 2.4. Docker Volumes

При запуске автоматически создаются и подключаются следующие именованные тома:

- **`frog_images`** → `/app/data/frogs` — хранит все сгенерированные изображения жабы
- **`prompt_storage`** → `/app/data/prompts` — файловое хранилище промптов GigaChat
- **`beat_data`** → `/app/data/beat` — состояние расписания Celery Beat
- **`postgres_data`** — данные PostgreSQL
- **`redis_data`** — данные Redis

## Шаг 3: Миграция Базы Данных (Первый Запуск)

При первом запуске необходимо инициализировать схему базы данных. Функция `ensure_schema()` идемпотентна и безопасна для повторного запуска.

### 3.1. Выполнение миграций

```bash
make migrate
```

Эта команда:
- Запустит контейнер бота в одноразовом режиме (`--rm`)
- Выполнит инициализацию схемы PostgreSQL
- Создаст все необходимые таблицы и индексы
- Автоматически удалит контейнер после завершения

**Примечание:** Миграции также автоматически выполняются при старте бота, но явный запуск рекомендуется для проверки корректности подключения к БД.

### 3.2. Проверка подключения к базе данных

```bash
# Подключение к PostgreSQL через контейнер
docker compose exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# Или проверка через Python в контейнере бота
docker compose exec bot python3 -c "from utils.postgres_client import init_postgres_pool; import asyncio; asyncio.run(init_postgres_pool())"
```

## Шаг 4: Тестирование

### 4.1. Запуск тестов

Для запуска тестов используется отдельный тестовый стек (см. `tests/docker-compose.test.yml`):

```bash
# Запуск unit-тестов (локально, без контейнеров)
make test-unit

# Запуск integration-тестов (требует поднятия тестовых контейнеров)
make test-integration

# Запуск всех тестов через полный CI-пайплайн
make ci
```

### 4.2. Запуск тестов через Docker Compose

Если вы хотите запустить тесты в основном контейнере бота:

```bash
# Убедитесь, что pytest установлен в образе
docker compose run --rm bot pytest tests/ -v
```

**Примечание:** Для полного набора тестов рекомендуется использовать команды из `Makefile`, которые используют специализированный тестовый стек.

### 4.3. Проверка качества кода

```bash
# Линтинг
make lint

# Проверка типов
make type

# Проверка форматирования
make format-check
```

## Дальнейшие шаги

### Полезные команды

```bash
# Остановка всех сервисов
docker compose down

# Остановка с удалением volumes (⚠️ удалит все данные!)
docker compose down -v

# Перезапуск конкретного сервиса
docker compose restart bot

# Просмотр логов конкретного сервиса
docker compose logs -f celery_worker

# Выполнение команды в контейнере
docker compose exec bot python3 -c "print('Hello from container')"
```

### Дополнительная документация

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Подробное описание архитектуры проекта
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Инструкции по развёртыванию в продакшн
- **[MONITORING.md](MONITORING.md)** — Настройка мониторинга и метрик
- **[API_REFERENCE.md](API_REFERENCE.md)** — Справочник по API и командам бота

### Получение токенов и ключей

Если вы ещё не получили необходимые токены:

1. **Telegram Bot Token:**
   - Найдите [@BotFather](https://t.me/BotFather) в Telegram
   - Отправьте команду `/newbot` и следуйте инструкциям

2. **Kandinsky API Keys:**
   - Зарегистрируйтесь на [https://fusionbrain.ai](https://fusionbrain.ai)
   - Перейдите в раздел "API" и скопируйте API Key и Secret Key

3. **Chat ID:**
   - Для личного чата: используйте [@userinfobot](https://t.me/userinfobot)
   - Для группы/канала: добавьте [@userinfobot](https://t.me/userinfobot) в группу/канал

### Устранение неполадок

#### Бот не запускается

1. Проверьте логи:
   ```bash
   docker compose logs bot
   ```

2. Проверьте, что все сервисы запущены:
   ```bash
   docker compose ps
   ```

3. Убедитесь, что файлы secrets созданы:
   ```bash
   ls -la secrets/
   ```

#### Ошибки подключения к базе данных

1. Проверьте, что PostgreSQL запущен и здоров:
   ```bash
   docker compose ps postgres
   docker compose logs postgres
   ```

2. Проверьте переменные окружения в `.env`:
   ```bash
   grep POSTGRES .env
   ```

3. Убедитесь, что пароль в `secrets/postgres_password` совпадает с `POSTGRES_PASSWORD` в `.env`

#### Ошибки при выполнении миграций

1. Убедитесь, что база данных доступна:
   ```bash
   docker compose exec postgres pg_isready -U ${POSTGRES_USER}
   ```

2. Проверьте права доступа к файлам secrets:
   ```bash
   chmod 600 secrets/postgres_password
   ```

---

**Приятного использования Wednesday Frog Bot! 🐸**
