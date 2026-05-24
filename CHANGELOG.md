# Changelog

## [Unreleased]

### Changed

**Monitoring**
- Перестроен `monitoring/` под Grafana + VictoriaMetrics + Vector + Loki.
- Удалены Prometheus/celery/frog dashboards; добавлены `monitoring/vm/scrape.yml` (promscrape VM), `wednesday-runtime.json` с inline PromQL.
- Алерты только в Grafana provisioning.
- Vector парсит JSON loguru (`record.extra`, `record.level.name`) для Loki labels.

**Infra / persistence**
- `PersistenceContainer`: убраны `_db_engine` и `_session_factory` из DI; снаружи остаётся только `uow_factory` (`SQLAUoWFactory`).
- `SQLAUoWFactory`: создание async engine и sessionmaker, wiring DB-метрик, `aclose()` для dispose engine; модульные `create_engine` / `close_engine` удалены.
- `UoWFactory`: в протокол добавлен `aclose()` для жизненного цикла engine.
- Shutdown `PersistenceContainer`: закрытие PostgreSQL через `uow_factory.aclose()` вместо прямого доступа к engine.
- Тесты: `tests/inf/di/`, `tests/inf/persistence/sqla/test_factory.py`, `tests/inf/observe/prometheus/test_adapters_sqla.py`.
