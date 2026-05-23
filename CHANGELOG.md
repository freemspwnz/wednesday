# Changelog

## [Unreleased]

### Changed

**Infra / persistence**
- `PersistenceContainer`: убраны `_db_engine` и `_session_factory` из DI; снаружи остаётся только `uow_factory` (`SQLAUoWFactory`).
- `SQLAUoWFactory`: создание async engine и sessionmaker, wiring DB-метрик, `aclose()` для dispose engine; модульные `create_engine` / `close_engine` удалены.
- `UoWFactory`: в протокол добавлен `aclose()` для жизненного цикла engine.
- Shutdown `PersistenceContainer`: закрытие PostgreSQL через `uow_factory.aclose()` вместо прямого доступа к engine.
- Тесты: `tests/inf/di/`, `tests/inf/persistence/sqla/test_factory.py`, `tests/inf/observe/prometheus/test_adapters_sqla.py`.

## [7.1.1] — 2026-05-22

### Fixed

**Presentation**
- `AdminAccessFilter`: в `__call__` добавлен аргумент `event: TelegramObject` перед `user: UserContext`. Aiogram передаёт апдейт первым позиционным аргументом; без `event` возникал `TypeError: got multiple values for argument 'user'` на всех `message`, проходящих через `admin_router`.
- Тест: `tests/pres/_aiogram/filters/test_access.py` — вызов фильтра с `event=...`, как в рантайме.

**Monitoring**
- Unit-тест `HighGenerationErrorRate` в `monitoring/prometheus/rules/metrics-rules.test.yml`: удлинены `input_series` и `eval_time: 12m`, чтобы учесть `rate[5m]` и `for: 5m` — стабильный проход `promtool test rules` в CI.
