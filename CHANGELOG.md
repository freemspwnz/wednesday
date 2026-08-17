# Changelog

## [Unreleased]

### Changed

**Infrastructure**
- Корневой compose-файл переименован: `docker-compose.yml` → `compose.yml` (Compose v2 default).
- В `.env.example` для metrics задан `METRICS__HOST=0.0.0.0` — bind для scrape из Docker network.

## [7.4.0] — 2026-08-14

### Added

**Observability**
- Стек мониторинга: Loki 3.x (TSDB/v13, retention 14d) + Vector + Grafana в `monitoring/docker-compose.yml`.
- Vector: wednesday-only `vector.yaml`, парсинг loguru JSON, лейблы Loki `service`/`env`/`level`.
- Grafana alerts: `noDataState: OK`, `ExporterDown` по `up{job="wednesday"}`, LogQL suspicious-secrets как в UI.

### Changed

**Infrastructure**
- Сборка и зависимости: Poetry → uv (PEP 621 + hatchling, `uv.lock`, CI `uv sync`, Docker `.venv`).
- `asyncbreaker` 2.1.x: адаптер под новый API, app-протоколы без изменений.

**CI**
- `dependency-review-action` v5 (Node 24).

### Fixed

**Application**
- `/generate` пишет `(chat_id, image_id)` в `image_view` в том же UoW, что и save каталога — `/random` в этом чате не показывает только что сгенерированную картинку; другие чаты её ещё могут получить.

**Presentation**
- Ожидаемые `DomainError` (cooldown и т.п.) в handler wrapper логируются как INFO, а не WARNING.
- В логах `Command/Callback handler failed` модуль берётся из имени команды / префикса callback — в Loki больше не `module=unknown`.
