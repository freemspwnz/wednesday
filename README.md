# Wednesday Frog Bot 🐸

[![CI](https://img.shields.io/github/actions/workflow/status/freemspwnz/wednesday/ci.yml?branch=main&logo=github&label=CI)](https://github.com/freemspwnz/wednesday/actions?query=event%3Apush+branch%3Amain+workflow%3ACI)
[![Coverage](https://codecov.io/gh/freemspwnz/wednesday/branch/main/graph/badge.svg)](https://codecov.io/gh/freemspwnz/wednesday)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Telegram-бот с асинхронной архитектурой (aiogram 3, SQLAlchemy async, Redis, Prometheus).

**Бот в Telegram:** [@wednesday_morning_bot](https://t.me/wednesday_morning_bot)

---

## Быстрый старт

```bash
git clone https://github.com/freemspwnz/wednesday.git
cd wednesday
uv sync --group dev
cp .env.example .env
```

Отредактируйте `.env`: `TELEGRAM__TOKEN`, `TELEGRAM__ADMIN_ID`, креды Postgres и Redis (шаблон — в `.env.example`).

Для локального запуска с хоста при Postgres/Redis в Docker: `POSTGRES__HOST=localhost`, `REDIS__HOST=localhost` (порт проброшен на машину). Внутри compose-сети — `postgres` / `redis`, как в примере для контейнеров.

Для dev без HTTP endpoint Prometheus оставьте `METRICS__ENABLED=false`. Если `true` — exporter обязан подняться, иначе процесс завершится до polling.

Поднимите Postgres и Redis, затем:

```bash
make migrate    # alembic upgrade head — схема wednesday_schema
make run
```

### Docker

В `compose.yml` сервисы Postgres/Redis по умолчанию закомментированы — нужны внешние инстансы в сети `wednesday` или раскомментируйте сервисы в compose. Миграции выполняются в `docker-entrypoint.sh` перед `main.py`.

При `METRICS__ENABLED=true` в контейнере задайте `METRICS__HOST=0.0.0.0`, чтобы VictoriaMetrics могла скрейпить `http://wednesday:8080/metrics` по сети `monitoring`. Порт на host пробрасывать не нужно.

Каталоги моделей/подписок не запекаются в образ и должны монтироваться в контейнер read-only:

- `./catalog:/app/catalog:ro`

Также задайте явные пути к YAML-каталогам (иначе будут использованы относительные дефолты):

- `YAML__MODELS_PATH=/app/catalog/models.yaml`
- `YAML__SUBSCRIPTIONS_PATH=/app/catalog/subscriptions.yaml`

```bash
make build      # образ wednesday:local
docker compose up -d --build
```

После изменения `volumes`/`environment` в compose выполните пересоздание контейнера, например:

```bash
docker compose up -d --force-recreate
```

Изменение файлов `catalog/*.yaml` не требует rebuild образа — достаточно перезапустить сервис:

```bash
docker compose restart wednesday
```

---

## Архитектура (v7)

```
wednesday/
├── main.py                 # Composition root: Config → Container → polling + catalog scheduler
├── app/                    # DTO, протоколы, исключения приложения
├── domain/                 # Агрегаты и доменная логика
├── infra/                  # Config, DI, persistence, observe, resilience
└── presentation/aiogram/   # Bot, dispatcher, routers, scheduler, middlewares

alembic/                    # Миграции PostgreSQL (схема wednesday_schema)
catalog/                    # Каталоги подписок и доступных моделей
tests/                      # Тесты
```

Слои **не смешиваются**: эволюция схемы — только Alembic; runtime — `main.py` + DI.

Расписание чата исполняется в том же процессе, что и polling: раз в минуту тикер шлёт unseen-фото из каталога (без GigaChat). Если чат уже всё посмотрел — текстовый notice с `/generate`, не silent skip. Просмотр записывается только после успешной отправки в Telegram.

---

## Миграции БД

| Команда | Назначение |
| --- | --- |
| `make migrate` | Применить все ревизии (`alembic upgrade head`) |
| `make migrate-revision MSG=add_foo` | Сгенерировать ревизию из diff ORM ↔ БД |

`revision --autogenerate` сравнивает `Base.metadata` (модели в `infra/persistence/sqlalchemy/models/`) с реальной БД и пишет файл в `alembic/versions/`. Нужна доступная Postgres и `.env` с `POSTGRES__*`. После автогенерации ревизию **просматривают вручную** — Alembic не угадывает переименования и data-migrations.

Пустая БД: `make migrate`. В Docker то же делает entrypoint перед стартом бота.

---

## Конфигурация

Настройки через `.env` с разделителем `__` (pydantic-settings). Минимум для dev:

```env
ENV=DEV
TELEGRAM__TOKEN=...
TELEGRAM__ADMIN_ID=123456789
POSTGRES__HOST=localhost
POSTGRES__PASSWORD=...
REDIS__HOST=localhost
REDIS__PASSWORD=...
METRICS__ENABLED=false
```

Для бота rate limit и retry — из `TELEGRAM__RATE_LIMIT__*` и `TELEGRAM__RETRY__*`, не из корневых `RATE_LIMIT__` / `RETRY__`. В `ENV=PROD` валидатор требует в том числе `METRICS__ENABLED=true` и `TELEGRAM__RATE_LIMIT__STORAGE=redis`.

Для Docker/Compose рекомендуется всегда задавать `YAML__MODELS_PATH` и
`YAML__SUBSCRIPTIONS_PATH` абсолютными путями внутри контейнера.

Полный перечень переменных: `.env.example`.

---

## Разработка

```bash
make lint          # ruff check
make type          # mypy
make test          # pytest
make test-cov      # pytest + coverage
make build         # docker image
make run           # uv run python wednesday/main.py
```

CI (`.github/workflows/ci.yml`): lint, format, mypy, pytest — без шага `migrate` (тесты persistence на моках).

---

## Документация

Описание v7 — этот README (структура, миграции, конфиг, команды `make`).

Исторические материалы (архитектура и стек до v7):

- [docs/release-notes/](docs/release-notes/) — заметки по релизам v6 и ранее
- [CHANGELOG.md](CHANGELOG.md) — изменения текущей ветки

Отдельные гайды (`INSTALLATION`, `DEPLOYMENT`, `ARCHITECTURE` в `docs/`) пока не вынесены.

---

## Лицензия

MIT License
