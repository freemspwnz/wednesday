# Wednesday Frog Bot 🐸

Автоматический Telegram-бот для еженедельной отправки сгенерированных изображений жабы с мемами про среду.

## Описание

Wednesday Frog Bot — полнофункциональный Telegram бот, который использует нейросеть Kandinsky для генерации разнообразных изображений жабы и автоматически отправляет их в указанные чаты каждую среду в заданное время.

### Возможности

- 🐸 **Автоматическая генерация** изображений жабы с помощью ИИ (Kandinsky API)
- 🧠 **Креативные промпты через GigaChat** (с fallback на статические)
- 📅 **Гибкое планирование** — настраиваемые временные слоты в среду (по умолчанию 09:00, 12:00, 18:00)
- 🌍 **Поддержка часовых поясов** — работает в любой временной зоне
- 💬 **Мультичат-рассылка** — отправка в несколько чатов одновременно
- 🎨 **Разнообразные стили** и промпты (динамически генерируются)
- 📊 **Метрики и мониторинг** — отслеживание производительности и использования
- 🚦 **Rate limiting** — защита от злоупотреблений
- ⚡ **Circuit breaker** — автоматическая защита от сбоев API
- 🔐 **Админ-команды** — управление ботом через Telegram
- 🔄 **Резервный SupportBot** — автоматическое переключение, единое статусное сообщение при запуске/остановке
- 📝 **Подробное логирование** с ротацией и архивацией
- 🧪 **Dry-run проверки API** (Kandinsky и GigaChat) без траты токенов/генераций
- 🎯 **Дублирование защиты** — предотвращение повторных отправок
- ⏱️ **Graceful shutdown** — корректное завершение работы

## Быстрый старт

1. **Клонируйте репозиторий**
```bash
git clone https://github.com/your-username/wednesday-tg-bot.git
cd wednesday-tg-bot
```

2. **Установите зависимости**
```bash
pip install -r requirements.txt
```

3. **Настройте конфигурацию**
```bash
cp env_example.txt .env
# Отредактируйте .env и добавьте токены
```

4. **Запустите бота**
```bash
python main.py
```

## Основные команды

### Пользовательские команды

- `/start` — Приветствие и информация о боте
- `/help` — Справка по пользовательским командам
- `/frog` — Сгенерировать жабу сейчас (с rate limiting)

### Админ-команды (требуют `ADMIN_CHAT_ID`)

- `/status` — Статус бота (dry-run проверки API, метрики, текущие модели)
- `/force_send` — Принудительная отправка в подключенные чаты
- `/add_chat <chat_id>` — Добавить чат в рассылку
- `/remove_chat <chat_id>` — Удалить чат из рассылки
- `/list_chats` — Список активных чатов с ID
- `/set_kandinsky_model <pipeline_id|name>` — Установить модель Kandinsky
- `/set_gigachat_model <model_name>` — Установить модель GigaChat
- `/list_models` — Показать доступные модели (обе системы)
- `/mod <user_id>` — Выдать права админа
- `/unmod <user_id>` — Убрать права админа
- `/list_mods` — Список админов
- `/set_frog_limit <threshold>` — Настроить общий лимит ручных `/frog` (1..100, ограничено квотой)
- `/set_frog_used <count>` — Установить текущее количество ручных `/frog` за месяц

## Структура проекта

```
wednesday_tg_bot/
├── main.py                      # Точка входа с graceful shutdown
├── bot/
│   ├── wednesday_bot.py         # Основной класс бота
│   ├── support_bot.py           # Резервный бот (SupportBot) и логика переключения
│   └── handlers.py              # Обработчики команд и сообщений
├── services/
│   ├── image_generator.py       # Генератор изображений (Kandinsky + dry-run)
│   ├── prompt_generator.py      # Клиент GigaChat для генерации промптов
│   ├── scheduler.py             # Планировщик задач с часовыми поясами (legacy)
│   ├── celery_app.py            # Конфигурация Celery (брокер, beat schedule)
│   └── celery_tasks.py          # Celery задачи (send_frog, generate_image, cleanup)
├── utils/
│   ├── config.py                # Конфигурация и валидация
│   ├── logger.py                # Настройка логирования (loguru)
│   ├── redis_client.py          # Асинхронный Redis‑клиент с in‑memory fallback
│   ├── postgres_client.py       # Пул подключений к PostgreSQL (asyncpg)
│   ├── postgres_schema.py       # Инициализация/миграция схемы БД
│   ├── chats_store.py           # Хранилище активных чатов (PostgreSQL)
│   ├── usage_tracker.py         # Отслеживание использования API (PostgreSQL)
│   ├── dispatch_registry.py     # Реестр отправок (anti-duplicate, PostgreSQL)
│   ├── models_store.py          # Текущее/доступные модели для Kandinsky/GigaChat (PostgreSQL)
│   ├── admins_store.py          # Дополнительные администраторы (PostgreSQL)
│   └── metrics.py               # Метрики производительности (PostgreSQL)
├── data/
│   └── frogs/                   # Генерированные изображения (архив, в Docker — volume frog_images → /app/data/frogs)
├── logs/                        # Логи с ротацией (в Docker — volume logs → /app/logs)
├── requirements.txt             # Зависимости
├── .env                         # Конфигурация (создается пользователем)
└── README.md                    # Этот файл
```

## Celery (Планировщик задач)

Проект использует Celery для планирования и выполнения периодических задач. Celery заменяет старый `TaskScheduler` и предоставляет более надёжное планирование с поддержкой распределённых worker'ов.

### Архитектура

- **Celery Beat** — планировщик, который создаёт задачи по расписанию
- **Celery Worker** — исполнитель задач (поддерживает async через `celery[asyncio]`)
- **Redis** — брокер и backend для очередей задач

### Запуск через Docker Compose

```bash
# Запуск всех сервисов (бот + Celery worker + Celery beat)
docker-compose up -d

# Просмотр логов Celery worker
docker-compose logs -f celery-worker

# Просмотр логов Celery beat
docker-compose logs -f celery-beat
```

### Запуск вручную (для разработки)

```bash
# В отдельном терминале: запуск Celery worker
celery -A services.celery_app worker --pool=threads --loglevel=info --concurrency=8 -Q wednesday,images,maintenance

# В другом терминале: запуск Celery beat
celery -A services.celery_app beat --loglevel=info
```

### Очереди задач

- `wednesday` — отправка жаб по средам (concurrency: 6)
- `images` — генерация изображений (concurrency: 2)
- `maintenance` — ежедневные задачи очистки и статистики (concurrency: 1)

### Конфигурация Celery

Переменные окружения для настройки Celery (см. `env_example.txt`):

```env
# Timezone для Celery Beat
SCHEDULER_TZ=Europe/Amsterdam

# Worker настройки
WORKER_CONCURRENCY=8
WORKER_PREFETCH_MULTIPLIER=1

# Beat настройки
BEAT_MAX_LOOP_INTERVAL=10

# Retry настройки
CELERY_TASK_MAX_RETRIES=3
CELERY_TASK_RETRY_BACKOFF=True
CELERY_TASK_RETRY_BACKOFF_MAX=600
```

### Мониторинг

- **Healthcheck**: `/health` endpoint включает проверку доступности Celery workers
- **Prometheus метрики**: `celery_tasks_total`, `celery_task_duration_seconds`, `celery_task_retries_total`
- **Логирование**: все задачи логируются через Loguru с структурированными событиями

## Конфигурация

### Обязательные переменные

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
KANDINSKY_API_KEY=your_api_key_here
KANDINSKY_SECRET_KEY=your_secret_key_here
CHAT_ID=your_chat_id_here
```

### Опциональные переменные

```env
# Уровень логирования (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# Времена отправки в среду (через запятую)
SCHEDULER_SEND_TIMES=09:00,12:00,18:00

# Часовой пояс для расписания
SCHEDULER_TZ=Europe/Moscow

# День недели (0=понедельник, 2=среда)
SCHEDULER_WEDNESDAY_DAY=2

# Таймаут генерации (секунды)
GENERATION_TIMEOUT=60

# Максимум попыток генерации
MAX_RETRIES=3

# ID администратора для админ-команд
ADMIN_CHAT_ID=your_admin_chat_id

# Подключение к PostgreSQL (совместимо с docker-compose.yml)
POSTGRES_USER=your_postgres_user
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=wednesdaydb
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Подключение к Redis (опционально, для кэша/лимитеров)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password  # опционально, оставьте пустым если без пароля

# Прокси для API запросов
HTTPS_PROXY=http://proxy:port
HTTP_PROXY=http://proxy:port

# Тестовый режим (запуск каждые N минут)
SCHEDULER_TEST_MINUTES=0
```

## Системные особенности

### Защита от дублирования

Система `DispatchRegistry` отслеживает все отправки по тайм-слотам и предотвращает повторную отправку в один и тот же чат в один временной слот.

### Отслеживание использования

`UsageTracker` ведет учет генераций по месяцам с настраиваемыми лимитами:
- Общая квота: 100 генераций в месяц (по умолчанию)
- Порог `/frog`: 70 генераций (после этого команда отключается)
- Автоматические отправки не ограничиваются порогом
- Настройки квоты и порога сохраняются в PostgreSQL и остаются после перезапуска

### Circuit Breaker

При множественных ошибках API система автоматически переходит в режим ожидания (5 минут) для защиты от перегрузки.

### Rate Limiting

Команда `/frog` защищена от злоупотреблений:
- На пользователя: минимум 5 минут между запросами
- Глобально: максимум 10 запросов в минуту
- Администратор может вручную корректировать порог и текущую выработку через `/set_frog_limit` и `/set_frog_used`

### Переключение SupportBot ↔ основной бот

- Статусное сообщение в не-админских чатах проходит три стадии:
  1. SupportBot: “🚀 Запускаю основной бот...”
  2. SupportBot при своём выключении добавляет “🛑 Support Bot остановлен”
  3. Основной бот после запуска заменяет сообщение на “🛑 Support Bot остановлен\n✅ Wednesday Frog Bot запущен”
- В админском чате отправляются только полные итоговые сообщения, без редактирования

### Мультичат

Бот автоматически:
- Добавляет чаты, в которых был добавлен
- Отправляет приветственное сообщение
- Удаляет чаты, из которых был удален
- Рассылает во все активные чаты одновременно

## Технологии

- **Python 3.8+** — основной язык
- **python-telegram-bot 22.5** — работа с Telegram API
- **Kandinsky API** — генерация изображений через Fusion Brain
- **loguru** — расширенное логирование
- **aiohttp** — асинхронные HTTP запросы
- **Pillow** — обработка изображений
- **python-dotenv** — управление конфигурацией

## Требования

- Python 3.8 или выше
- Токен Telegram бота
- Ключи Kandinsky API (Fusion Brain)
- Доступ к интернету
- 100MB свободного места на диске

## Установка и запуск

Подробную инструкцию см. в `docs/INSTALLATION.md`. Кратко:

```bash
git clone https://github.com/your-username/wednesday-tg-bot.git
cd wednesday-tg-bot
cp env_example.txt .env
# отредактировать .env

# Запуск через docker-compose (Postgres + Redis + бот + Docker volumes)
docker compose up -d --build
```

### Docker volumes и файловое хранилище

При запуске через `docker compose` автоматически создаются и подключаются три именованных тома:

- **frog_images** — монтируется в контейнер по пути `/app/data/frogs` и используется
  для хранения сгенерированных изображений жабы (команды `/frog`, `/force_send` и fallback‑архив).
- **logs** — монтируется в контейнер по пути `/app/logs` и содержит все файлы логов
  (`wednesday_bot_YYYY-MM-DD.log` с ротацией и сжатием).
- **prompt_storage** — монтируется в контейнер по пути `/app/data/prompts` и используется
  файловым хранилищем промптов GigaChat. Все промпты пишутся только в этот volume
  (директорию `/app/data/prompts`), а не в образ контейнера.

Для резервного копирования достаточно сохранять содержимое этих томов. Примеры:

```bash
# Резервная копия изображений и логов (host‑директории по умолчанию)
docker compose run --rm bot sh -c 'ls -R /app/data/frogs /app/logs'

# Бэкап тома frog_images в tar (извне контейнера)
docker run --rm -v wednesday_tg_bot_frog_images:/data -v "$PWD":/backup alpine \
  sh -c "cd /data && tar czf /backup/frog_images_backup.tgz ."

# Аналогично можно сделать бэкап томов logs и prompt_storage
```

## Безопасность

- Все токены хранятся в `.env` (исключен из Git)
- Валидация конфигурации при запуске
- Graceful shutdown при остановке
- Защита от злоупотреблений API
- Логирование без утечки чувствительных данных

## Производительность

- Асинхронные операции для максимальной эффективности
- Переиспользование HTTP соединений
- Кэширование pipeline ID
- Параллельная отправка в несколько чатов
- Экспоненциальный backoff при ошибках

## Мониторинг

- Логи с ротацией (1 день) и сжатием (zip)
- Метрики производительности в JSON
- Dry-run проверки API в `/status` (только админ)
- Статистика использования
- Circuit breaker триггеры

## Поддержка

При возникновении проблем:

1. Проверьте логи в `logs/`
2. Убедитесь в корректности конфигурации
3. Проверьте подключение к интернету
4. Создайте issue в репозитории

## Лицензия

MIT License

---

**Сделано с ❤️ для мемов про среду 🐸**

## Миграции БД и схема

- **Схема PostgreSQL** описана в модуле `utils/postgres_schema.py` и SQL-файлах в `docs/sql/`.
- Для инициализации/обновления схемы используйте:

```bash
make migrate
```

Эта команда вызывает `python -m utils.postgres_schema` с параметрами подключения из окружения
(`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`) и
идемпотентно создаёт все необходимые таблицы.

## Тесты и CI

- Для локального запуска тестов с использованием тестовой Postgres/Redis (через `docker-compose.test.yml`):

```bash
make test        # junit.xml
make test-cov    # junit.xml + coverage.xml
```

- Для быстрой проверки без контейнеров (если тестовая БД уже запущена локально):

```bash
make test-no-containers
```

- Полный локальный CI-пайплайн (lint + type + migrate + tests + build Docker image):

```bash
make ci
```

### GitHub Actions

- Основной workflow CI расположен в `.github/workflows/ci.yml` и выполняет шаги:
  - установка зависимостей и запуск `ruff` (lint);
  - запуск `mypy` (type-check);
  - `make migrate` (инициализация схемы в тестовой БД);
  - `make test-cov` (pytest с покрытием);
  - `make build` (сборка Docker-образа бота).

CI использует сервисные контейнеры PostgreSQL и Redis в job, что гарантирует доступность
volume-backed путей и стабильное окружение для тестов.
