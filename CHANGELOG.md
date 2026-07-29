# Changelog

## [7.3.0] — 2026-07-29

### Added

**Domain**
- Image BC: management (`hide`/`show` + `ManagementAccessPolicy`), generation (`ImageGenerationService`, prompt pipeline), moderation промптов (`PromptModerationPolicy`).
- `ManagementAccessPolicy`: ADMIN — только hide; OWNER/SYSTEM — hide+show.
- VO/events: `ImagePrompts` / `PromptSource` / `ImageRender`, `HiddenState`/`HiddenReason`, `ImageHidden`/`ImageShown`.
- `ImageRating` VO и `ImageRatingPolicy` (net rating вместо целочисленного score); `ImageLifecycleService.apply_vote`.
- Доменные сервисы user/chat: lifecycle, management, schedule, moderation; `UserGenerationService` (выбор модели + доступ к генерации).
- Порты `PromptCatalog`, `Generator`, `ViewRepo`; `VoteRepo.reset` / `get_if_exists`; `Vote.voter_id: UserId`.

**Infrastructure**
- Alembic `ea4c99f0601f`: `status`→`state`, `votes`→`score`→`likes`/`dislikes`, `user_prompt`→`primary_prompt` + `prompt_source`; `image_seen`→`image_view`; NOT NULL на `telegram_file_id` / `primary_prompt`.
- `YamlPromptCatalog` + `catalog/prompts.yaml` (system prompts и fallback components).
- Network layer на httpx2: `HttpClient` / factory / policy / registry; Sber/GigaChat (`SberAuth`, `SberClient`) через `NetworkContainer` (nested config + PROD checks; shutdown закрывает providers).
- HTTP-метрики (`HttpxMetrics`: duration/totals по method/url/outcome/status).

**Application**
- Capability-scoped image UC: `ImageCatalogUseCase`, `ImageVoteUseCase`, `ImageManagementUseCase`, `ImageGenerationUseCase` (+ `ImageBaseUseCase`; HTTP render вне UoW, `register` после отправки).
- Capability-scoped user UC: `lifecycle` / `management` / `moderation` / `generation` (`assert_allowed` / `record_usage`, `assign_ban`).
- Capability-scoped chat UC: `management` / `schedule`.
- Тонкие UC поверх доменных сервисов (app оставляет UoW / cache / DTO / logging).

**Presentation**
- Роутеры и messages разбиты на модули: `chat/` → `chat_member` / `management` / `schedule`; `user/` package; `image/vote/`; `messages/common.py`, `messages/image.py`, `messages/user/`; `error.py` → `errors.py`; `retry_predicate.py` → `predicate.py`.

### Changed

**Domain**
- Командная логика перенесена из app-сервисов в domain services; app UC тонкие.
- `Image._score` → `Image._rating` (`ImageRating`); событие `ImageScoreRecalculated` → `ImageRatingChanged`.
- `ImageGenerator` + `TextGenerator` объединены в `Generator`; `FallbackService` влит в generation service.
- `ImageCatalogService.pick_for_chat` делегирует unseen-выбор в `ViewRepo`.
- Usage: `assert_allowed` только проверка; списание через `record_usage` после успеха.
- `UsageRepo`: `get_stats` / `record` (вместо `get_usage_stats` / `record_usage`).

**Infrastructure**
- ORM/repos под rating и views: `SQLAViewRepo.get_unseen_for_chat`, маппинг likes/dislikes; `pick_random` убран с image repo.
- `ObserveContainer.collector` / `metrics_registry` → единый `metrics` (`PrometheusRegistry` владеет collector + `serve`); адаптеры `retry`/`cb`/`rl`/`cache`/`db`/`http`; `MetricsCollector.serve` убран.
- DB metrics: полная сигнатура SQLAlchemy cursor hooks на `DBMetrics`/`SQLAMetrics`.
- `RedisRepoRegistry` сам создаёт `RedisClient`; accessors `users`/`chats`.
- YAML package `catalog` → `catalogs`; factory accessors `models`/`subscriptions`/`prompts`; `PersistenceContainer.catalog` (был `catalog_factory`).
- Resilience factories: `retrier`/`breaker`/`limiter`; конфиги только явные (без root `Config.retry`/`rate_limit`/`circuit_breaker`).
- `TelegramConfig`: nested `retrier`/`limiter`; PROD check `TELEGRAM__LIMITER__STORAGE`; `RateLimitConfig` key `base_limit` → `base`.
- GigaChat: `cert`, `base_url` → `api.giga.chat`, rate limit 2/s; compose монтирует `./certs`.
- Logging: bootstrap в `get_logger`; убрана инъекция `user_id`/`chat_id`/`generation_id` (=None); extras `service`→`app`, `version`→`ver`; structured kwargs у limiter/breaker/retry; mute `httpcore2`.
- Каталоги prompts/models упрощены под текущий generation pipeline.

**Application**
- DI/Scope: `cache`/`catalog`/`uow` (был `uow_factory`); plural accessors; image/user/chat UC вместо монолитов.
- `ImageCard.score` → `ImageCard.rating`; `file_id` всегда `TelegramFileId`.
- Generation UC: единый `Generator`; `by_user` парсит raw prompt → `NormalizedPrompt`.
- Vote UC: duplicate → `None`; catalog UC: stale id → `ImageNotFoundError`; management `show()` сбрасывает votes для OWNER.
- Удалены `app/services` и app-level `UserNotFoundError`/`ChatNotFoundError` (domain NotFound).

**Presentation**
- Middleware/session: `rate_limiter`/`retry` → `limiter`/`retrier`.
- Admin-router поглощён management/user flows; `messages/admin.py` / монолитные builders убраны.
- `/random`: убрана ветка `IMAGE_UNAVAILABLE` (file_id всегда есть).
- Aiogram limits: user 3/s, chat 30/min.

### Fixed

- Usage не списывается до успешной генерации; rejected prompts не жгут слот и не стопорят strikes — `assign_ban` всегда пишет violation перед решением о бане.
- `from __future__ import annotations` возвращён там, где TYPE_CHECKING-импорты иначе дают `NameError`.
- GigaChat: `verify`/`http2` на `AsyncHTTPTransport` (иначе httpx игнорирует их при custom transport); default http2=false.
- CI: версия Poetry из repository variable `vars.POETRY_VERSION` (и ARG в Docker).

### Removed

- `ImageCommandsUseCase`, app `*CommandsService` / registration services.
- `ModelSelectionService` (влит в `UserGenerationService`).
- `ImageScorePolicy`, отдельные `ImageGenerator`/`TextGenerator`, `FallbackService`.
- `routers/admin.py`, `messages/admin.py` / `messages/commands.py` / монолитный `messages/user.py`.
- Root-level `Config.retry` / `rate_limit` / `circuit_breaker`.
- `MetricsCollector.serve`.
