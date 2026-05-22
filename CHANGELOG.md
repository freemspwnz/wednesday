# Changelog

## [Unreleased]

Write an up-to-date Redis user snapshot after successful UoW
commits for role, ban, subscription, and profile changes so
RegistrationMiddleware sees fresh UserContext without waiting
for cache TTL.

Show role, subscription limits, and ban status from UserContext
after registration middleware; format text in messages/profile.

Replace AdminAccessMiddleware with AdminAccessFilter on admin_router
(ADMIN/OWNER only, no denial message). Move rate-limit key builders into
ThrottlingMiddleware and RateLimitRequestMW as private static methods;
keep shared is_chat and require_request_scope in middlewares.utils.
Update presentation tests accordingly.

Move sqlalchemy.event wiring into create_engine; SQLAMetrics handles
cursor timing and Prometheus emission without importing sqlalchemy.
Pass db_metrics through the factory instead of registering from DI.

Add Codecov badge and tidy README tree comments

## [7.0.0]

### Added

**Domain**
- `domain/kernel` — базовые VO и исключения.
- `domain/user` — агрегат User, роли, подписка, бан/разбан, политики управления (`ManagementAccessPolicy`), сервисы `GenerationAccessService` и `UserModerationService`, события.
- `domain/chat` — агрегат Chat, расписание, lifecycle, `ChatMember` / `ManagementAccessPolicy`, `ChatRepo`.
- Тесты: `tests/dom/kernel`, `tests/dom/user`, `tests/dom/chat`.

**Application**
- DTO `UserContext` / `ChatContext` (доменный UUID и Telegram id раздельно, `from_domain`).
- Иерархия исключений `app.exceptions` (resilience, SQLA persistence, observe).
- Протоколы `app.protocols`: UoW, cache, retry, circuit breaker, rate limiter, logger, metrics.
- `RegistrationService` / `RegistrationUseCase` — регистрация user/chat (кэш Redis → Postgres, детерминированные id из `tg_id`).
- `UserCommandService` / `UserCommandsUseCase`, `ChatCommandService` / `ChatCommandsUseCase` — команды агрегатов через UoW.
- Тесты: `tests/app`.

**Infrastructure**
- `infra.config.Config` (BaseSettings, nested `__`), PROD-валидация (logging, metrics, postgres/redis, resilience storage, telegram).
- `infra.config.presentation.TelegramConfig` — token, admin_id, вложенные retry/rate_limit для Bot API.
- `infra.di.Container` — composition root (observe, persistence, resilience, `get_scope`, shutdown с таймаутами).
- Persistence: SQLAlchemy async (схема `wednesday_schema`, Chat/User ORM + сателлиты, репозитории с `ON CONFLICT`), Redis cache (snapshots, registry).
- Resilience: Tenacity retrier, asyncbreaker CB, limits rate limiter + фабрики и метрики.
- Observe: Loguru (структурированные `user_id` / `chat_id` / `generation_id`), Prometheus collector/registry и HTTP exporter.
- Тесты: `tests/inf` (config, di, persistence, resilience, observe).

**Presentation**
- Слой `presentation/aiogram`: `setup_bot` / `setup_dp`, middleware (DI, registration, throttling, admin access, session retry/rate limit), routers (`common`, `user`, `admin`, `chat_event`, errors).
- Команды: `/start`, `/help`, admin (activate/deactivate, mod/unmod, ban/unban, …), заглушки user, обработка `my_chat_member` / `chat_member`.
- Тесты: `tests/pres/_aiogram`.

**Runtime & ops**
- `wednesday/main.py` — точка входа: Config → Container → metrics → aiogram polling → graceful shutdown.
- Alembic: async `env.py`, initial revision `8593d284af18` (10 таблиц под текущие ORM-модели).
- `make migrate`, `make migrate-revision`, `make run`; миграции в `docker-entrypoint.sh` перед `main.py`.
- Alembic и `alembic.ini` в Docker-образе; обновлён README (v7, без ссылок на несуществующие `docs/*.md`).

### Changed

- Полный архитектурный reset: развитие с нуля до полного вертикального среза (domain → app → infra → presentation).
- CI: reusable workflows (ruff, mypy, pytest), coverage/junit из `make test-cov`, pre-commit через `make format` / `lint` / `type` / `test-cov`.

### Removed

- Legacy core, старые CI merge-скрипты и docker test helpers.
- Устаревшие разделы README (Celery, monolithic `utils/`, гайды в `docs/`).

### Fixed

- CI/workflow-call, permissions, poetry install.

### Notes

- `docs/` содержит только `release-notes/` (архив v6); актуальная документация — README и `.env.example`.
- Первый деплой БД: `make migrate` на пустой схеме.
- Локальный dev: `METRICS__ENABLED=false` рекомендуется, если HTTP exporter не нужен.
