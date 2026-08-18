# Changelog

## [Unreleased]

### Fixed

**Presentation**
- Throttle колбэков (👍/👎) больше не пишет шутку в чат: кликнувший получает персональный toast, спиннер не зависает. Флуд команд по-прежнему предупреждается сообщением.

## [7.5.0] — 2026-08-18

### Added

**Domain**
- Новые `ImageId` генерируются как UUIDv7 (RFC 9562) через `uuid-utils`; существующие v4/v5 не затронуты.

**Infrastructure**
- Startup fail-fast: если Postgres или Redis недоступен при старте, процесс завершается с ненулевым кодом (`DBUnavailableError` / `CacheUnavailableError`).

**CI**
- GitHub Release автоматически создаётся на `v*` тегах после публикации Docker-образа; notes берутся из `CHANGELOG.md`.

### Changed

**Domain**
- Константы валидации/политик вынесены из module-level на владеющий тип как `ClassVar` (frozen dataclass, VO, policy, service).

**Infrastructure**
- Infra-константы (shutdown timeout, metric prefix/namespace, retry/limiter labels) — на владеющем классе как `ClassVar`.
- Версия приложения берётся из `pyproject.toml` через `importlib.metadata`; хардкод версии убран из Config, HttpConfig, GigaChatConfig и тестов. `VERSION` env по-прежнему переопределяет.
- GigaChat text/image вызовы сериализованы через `Semaphore(1)` — GIGACHAT_API_PERS не принимает параллельные completions.
- HTTP error body (до 1 КБ) сохраняется на `HttpResponseError` и логируется — Sber 4xx причины видны в Loki без ручного повтора.
- Rate-limiter логи и метрики используют раздельные `limiter` + `bucket` вместо fused `name=telegram:chat`.
- Rate-limiter метрики записываются и при storage/unexpected ошибках (ранее таймер оставался открытым).
- Корневой compose-файл переименован: `docker-compose.yml` → `compose.yml` (Compose v2 default).
- `python3-dev` убран из Docker builder — на python:3.12-slim (Trixie) он тянул заголовки Python 3.13.
- Неиспользуемые Taskiq-остатки удалены из `pyproject.toml`.
- Неиспользуемый `expose` убран из wednesday-сервиса в compose.

**CI**
- Docker actions обновлены до Node 24 runtime train (setup-qemu/buildx/login v4, metadata v6, build-push v7).
- `setup-uv` обновлён до v7.

### Fixed

**Infrastructure**
- Rate-limiter: `on_error` фиксирует duration при сбое Redis/backend.
- HTTP client: truncated response body логируется при 4xx/5xx.
