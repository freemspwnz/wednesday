# Wednesday Frog Bot 🐸

[![Logo](assets/logo.png)](https://github.com/Freemspwnz/wednesday)
[![CI Status](https://github.com/Freemspwnz/wednesday/workflows/CI/badge.svg)](https://github.com/Freemspwnz/wednesday/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Codecov](https://codecov.io/gh/Freemspwnz/wednesday/branch/main/graph/badge.svg)](https://codecov.io/gh/Freemspwnz/wednesday_tg_bot)

---

## Краткое Описание

**Wednesday Frog Bot** — полнофункциональный Telegram-бот для автоматической генерации и отправки изображений жабы с мемами про среду. Бот использует нейросеть Kandinsky для генерации разнообразных изображений и автоматически отправляет их в указанные чаты каждую среду в заданное время.

**🔗 Попробуйте бота в Telegram:** [@wednesday_morning_bot](https://t.me/wednesday_morning_bot)

---

## 🚀 Быстрые ссылки

- [Установка для разработки](docs/INSTALLATION.md) — 5 минут до первого запуска
- [Развертывание в production](docs/DEPLOYMENT.md) — полное руководство
- [Справочник команд](docs/API_REFERENCE.md) — все команды бота
- [Архитектура проекта](docs/ARCHITECTURE.md) — как всё устроено

---

## Ключевые Возможности

| Категория | Возможности |
|-----------|-------------|
| 🐸 **Генерация изображений** | Автоматическая генерация через Kandinsky API, креативные промпты через GigaChat, поддержка нескольких моделей |
| 📅 **Планирование** | Гибкое планирование с настраиваемыми временными слотами (по умолчанию 09:00, 12:00, 18:00), поддержка часовых поясов |
| 💬 **Мультичат** | Автоматическая рассылка в несколько чатов одновременно, автоматическое добавление/удаление чатов |
| 🚦 **Защита и ограничения** | Rate limiting (per-user и global), защита от дублирования, circuit breaker для защиты от сбоев API |
| 🔐 **Администрирование** | Полный набор админ-команд через Telegram, управление чатами, моделями, администраторами и лимитами |
| 🔄 **Надежность** | Резервный SupportBot с автоматическим переключением, graceful shutdown, подробное логирование |
| 📊 **Мониторинг** | Метрики производительности, Prometheus экспорт, healthcheck endpoints, dry-run проверки API |
| ⚡ **Производительность** | Асинхронная архитектура, Celery для фоновых задач, PostgreSQL для персистентных данных, Redis для кэша |

### Детальный список возможностей

- 🐸 **Автоматическая генерация** изображений жабы с помощью ИИ (Kandinsky API)
- 🧠 **Креативные промпты через GigaChat** (с fallback на статические)
- 📅 **Гибкое планирование** — настраиваемые временные слоты в среду
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

---

## Начало Работы

### Быстрый старт для разработчиков

Для быстрого запуска проекта локально выполните следующие шаги:

1. **Клонируйте репозиторий**
   ```bash
   git clone https://github.com/your-username/wednesday-tg-bot.git
   cd wednesday-tg-bot
   ```

2. **Настройте конфигурацию**
   ```bash
   cp env_example.txt .env
   # Отредактируйте .env и добавьте необходимые токены и ключи
   ```

3. **Запустите через Docker Compose**
   ```bash
   docker compose up -d --build
   ```

4. **Выполните миграцию базы данных** (первый запуск)
   ```bash
   make migrate
   ```

> 📖 **Подробные инструкции по установке и настройке** см. в [**INSTALLATION.md**](docs/INSTALLATION.md)

---

## Документация

### 📚 Навигационный центр документации

Добро пожаловать в центр документации Wednesday Frog Bot! Здесь вы найдете все необходимые материалы для работы с проектом.

#### 🛠️ Для Разработчиков

| Документ | Описание |
|----------|----------|
| [**ARCHITECTURE.md**](docs/ARCHITECTURE.md) | Детальное описание архитектуры проекта, компонентов системы, потоков данных и диаграммы взаимодействия |
| [**INSTALLATION.md**](docs/INSTALLATION.md) | Подробное руководство по установке, настройке окружения и первому запуску проекта |
| [**PROJECT_SUMMARY.md**](docs/PROJECT_SUMMARY.md) | Краткий обзор проекта, ключевые технологии и функционал |
| [**TYPING_GUIDE.md**](docs/TYPING_GUIDE.md) | Руководство по типизации в проекте, использование type hints и best practices |
| [**TESTING_GUIDE.md**](docs/TESTING_GUIDE.md) | Руководство по написанию и запуску тестов, структура тестового стека |

#### 👨‍💼 Для Операторов и Администраторов

| Документ | Описание |
|----------|----------|
| [**DEPLOYMENT.md**](docs/DEPLOYMENT.md) | Полное руководство по развертыванию бота в production среде, настройка инфраструктуры, backup и restore |
| [**MONITORING.md**](docs/MONITORING.md) | Настройка мониторинга, метрик Prometheus, логирования через Loki, настройка алертов и дашбордов Grafana |
| [**LOKI_PROMTAIL_SCHEMA.md**](docs/LOKI_PROMTAIL_SCHEMA.md) | Схема структурированного логирования для Loki и Promtail, примеры LogQL-запросов |

#### 📖 Справочная документация

| Документ | Описание |
|----------|----------|
| [**API_REFERENCE.md**](docs/API_REFERENCE.md) | Полный справочник всех команд бота: пользовательские команды, административные команды, примеры использования |

#### 📝 Дополнительные материалы

- **CHANGELOG.md** — история изменений проекта
- **docs/release-notes/** — подробные заметки о релизах
- **docs/sql/** — SQL-скрипты для миграций базы данных

---

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

> 📖 **Полный справочник команд с примерами** см. в [**API_REFERENCE.md**](docs/API_REFERENCE.md)

---

## Технологический стек

- **Python 3.8+** с **Asyncio** — асинхронное программирование
- **PostgreSQL** — основное хранилище данных (чаты, метрики, использование, модели)
- **Redis** — кэширование и очереди для асинхронных задач
- **Celery** — распределенная система выполнения фоновых задач и планирования
- **Docker** — контейнеризация для упрощения развертывания
- **python-telegram-bot 22.5** — работа с Telegram API
- **Kandinsky API** — генерация изображений через Fusion Brain
- **GigaChat API** — генерация креативных промптов
- **loguru** — расширенное логирование
- **aiohttp** — асинхронные HTTP запросы
- **Pillow** — обработка изображений

---

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
├── docs/                        # Документация проекта
├── data/
│   └── frogs/                   # Генерированные изображения (архив)
├── logs/                        # Логи с ротацией
├── requirements.txt             # Зависимости
├── .env                         # Конфигурация (создается пользователем)
└── README.md                    # Этот файл
```

---

## Celery (Планировщик задач)

Проект использует Celery для планирования и выполнения периодических задач. Celery заменяет старый `TaskScheduler` и предоставляет более надёжное планирование с поддержкой распределённых worker'ов.

### Архитектура

- **Celery Beat** — планировщик, который создаёт задачи по расписанию
- **Celery Worker** — исполнитель задач (поддерживает async через `celery[asyncio]`)
- **Redis** — брокер и backend для очередей задач

### Очереди задач

- `wednesday` — отправка жаб по средам (concurrency: 6)
- `images` — генерация изображений (concurrency: 2)
- `maintenance` — ежедневные задачи очистки и статистики (concurrency: 1)

> 📖 **Подробнее о Celery и настройке** см. в [**ARCHITECTURE.md**](docs/ARCHITECTURE.md) и [**DEPLOYMENT.md**](docs/DEPLOYMENT.md)

---

## Конфигурация

### Обязательные переменные окружения

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
KANDINSKY_API_KEY=your_api_key_here
KANDINSKY_SECRET_KEY=your_secret_key_here
GIGACHAT_API_KEY=your_gigachat_api_key_here
ADMIN_CHAT_ID=your_admin_chat_id
POSTGRES_USER=your_postgres_user
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=wednesdaydb
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### Опциональные переменные

```env
# Уровень логирования (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# Времена отправки в среду (через запятую)
SCHEDULER_SEND_TIMES=09:00,12:00,18:00

# Часовой пояс для расписания
SCHEDULER_TZ=Europe/Moscow

# Redis настройки
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password
```

> 📖 **Полный список переменных окружения** см. в [**INSTALLATION.md**](docs/INSTALLATION.md)

---

## Тесты и CI/CD

### Локальный запуск тестов

```bash
# Запуск тестов с использованием тестовой Postgres/Redis
make test        # junit.xml
make test-cov    # junit.xml + coverage.xml

# Быстрая проверка без контейнеров (если тестовая БД уже запущена)
make test-no-containers

# Полный локальный CI-пайплайн (lint + type + migrate + tests + build)
make ci
```

### GitHub Actions

Основной workflow CI расположен в `.github/workflows/ci.yml` и выполняет:
- установка зависимостей и запуск `ruff` (lint)
- запуск `mypy` (type-check)
- `make migrate` (инициализация схемы в тестовой БД)
- `make test-cov` (pytest с покрытием)
- `make build` (сборка Docker-образа бота)

### Миграции БД

```bash
# Инициализация/обновление схемы БД
make migrate
```

Схема PostgreSQL описана в модуле `utils/postgres_schema.py` и SQL-файлах в `docs/sql/`.

---

## Системные особенности

### Защита от дублирования

Система `DispatchRegistry` отслеживает все отправки по тайм-слотам и предотвращает повторную отправку в один и тот же чат в один временной слот.

### Отслеживание использования

`UsageTracker` ведет учет генераций по месяцам с настраиваемыми лимитами:
- Общая квота: 100 генераций в месяц (по умолчанию)
- Порог `/frog`: 70 генераций (после этого команда отключается)
- Автоматические отправки не ограничиваются порогом

### Rate Limiting

Команда `/frog` защищена от злоупотреблений:
- На пользователя: минимум 5 минут между запросами
- Глобально: максимум 10 запросов в минуту

### Circuit Breaker

При множественных ошибках API система автоматически переходит в режим ожидания (5 минут) для защиты от перегрузки.

---

## Безопасность

- Все токены хранятся в `.env` (исключен из Git)
- Валидация конфигурации при запуске
- Graceful shutdown при остановке
- Защита от злоупотреблений API
- Логирование без утечки чувствительных данных

> 📖 **Рекомендации по безопасности в production** см. в [**DEPLOYMENT.md**](docs/DEPLOYMENT.md)

---

## Производительность

- Асинхронные операции для максимальной эффективности
- Переиспользование HTTP соединений
- Кэширование pipeline ID
- Параллельная отправка в несколько чатов
- Экспоненциальный backoff при ошибках
- Connection pooling для PostgreSQL

---

## Мониторинг

- Логи с ротацией (1 день) и сжатием (zip)
- Метрики производительности в JSON
- Prometheus экспорт метрик
- Healthcheck endpoints (`/health`)
- Dry-run проверки API в `/status` (только админ)
- Статистика использования
- Circuit breaker триггеры

> 📖 **Подробная настройка мониторинга** см. в [**MONITORING.md**](docs/MONITORING.md)

---

## Поддержка

При возникновении проблем:

1. Проверьте логи в `logs/` или через Grafana Loki
2. Убедитесь в корректности конфигурации (см. [**INSTALLATION.md**](docs/INSTALLATION.md))
3. Проверьте подключение к интернету и API сервисам
4. Проверьте метрики через Prometheus/Grafana
5. Создайте issue в репозитории

---

## Лицензия

MIT License

---

**Сделано с ❤️ для мемов про среду 🐸**
