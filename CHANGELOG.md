# Changelog
## [7.1.0] — 2026-05-22

### Added

**Presentation**
- Команда `/me` — профиль пользователя (роль, подписка, лимиты, статус бана) из `UserContext` после `RegistrationMiddleware`, без отдельного запроса в БД.
- Тексты в `presentation/aiogram/messages/profile.py`; команда в меню бота, WELCOME и HELP.
- Тесты: `tests/pres/_aiogram/test_profile.py`, `tests/pres/_aiogram/handlers/test_user.py`.

**Documentation**
- Badge Codecov в README (покрытие из CI → `coverage.xml`).

### Changed

**Application**
- `UserCommandsUseCase` — после успешных мутаций user-агрегата (`change_role`, `ban`, `unban`, `change_subscription`, `change_profile`, `expire_*`) обновляет Redis snapshot (`cache_registry.user.set`), чтобы следующий update видел актуальные роль/бан/подписку без ожидания TTL (~10 мин).

**Presentation**
- Доступ к admin-router: `AdminAccessFilter` на роутере (роли `ADMIN` / `OWNER` в `UserContext`), вместо `AdminAccessMiddleware` с `admin_id` и ответом «не админ».
- Rate-limit key helpers перенесены в `ThrottlingMiddleware` и `RateLimitRequestMW`; в `middlewares.utils` остаются только `is_chat` и `require_request_scope`.

**Infrastructure**
- `DBMetrics`: хуки жизненного цикла cursor (`on_before_cursor_execute`, `on_after_cursor_execute`, `on_cursor_error`) вместо `register(engine)`.
- `SQLAMetrics` — тайминг (weakref), разбор SQL-команды (regexp) и Prometheus без импорта SQLAlchemy.
- `create_engine` принимает `metrics: DBMetrics`, вешает `sqlalchemy.event` через `_attach_engine_metrics`; DI больше не вызывает `register` на engine отдельно.
- Тесты: обновлены `tests/inf/observe/prometheus/test_adapters_sqla.py`, `tests/inf/persistence/sqla/test_factory.py`.

### Fixed

- Устаревший `UserContext` в Redis после admin-команд (`/mod`, `/ban`, …) до истечения TTL — следующий `reg_user` отдавал старую роль/статус бана.

### Removed

- `AdminAccessMiddleware` и `presentation/aiogram/messages/access.py` (`ADMIN_DENIED`).
- `DBMetrics.register` и привязка SQLAlchemy event listeners в prometheus-адаптере.

### Notes

- Первый OWNER в проде — по-прежнему через SQL seed / ручную роль в БД; `TELEGRAM__ADMIN_ID` для startup/shutdown и не даёт доступ в admin-router без роли `ADMIN`/`OWNER`.
- Badge Codecov на `main` появится после успешного upload с `CODECOV_TOKEN` в CI.
