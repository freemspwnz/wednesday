# Changelog

## [7.2.0] — 2026-06-02

### Added

**Domain**
- Новый bounded context `image`: aggregate, vote flow, score policy, events и доменные ошибки.
- `domain/catalog`: vocabularies моделей/подписок + `ModelCatalog` / `SubscriptionCatalog` протоколы.
- `UserSettings`, `ModelSelectionPolicy`, `ModelSelectionService`; политика выбора модели по tier/active.
- Порты `UsageRepo` и `ViolationRepo` перенесены в `domain.user.protocols`.

**Infrastructure**
- SQLAlchemy persistence для `Image`, `UserSettings`, `Usage`, `Violation`.
- Alembic-миграция `fb548c333d1f` (таблицы `user_settings`, `images`, `image_votes`, `image_seen`, `user_usage`, `user_violations`) + backfill дефолтных user settings.
- YAML adapters для каталогов моделей/подписок (`YamlCatalogFactory`) с DI wiring.
- `UserSnapshot` v2: поля `model_vendor`, `model_series`, `model`.

**Application**
- `ImageCard` DTO для отправки фото + vote callbacks.
- Регистрация пользователя создаёт дефолтные `UserSettings` из каталогов.
- Единый `ImageCommandsUseCase` (`pick_for_chat` + `vote`) и `ImageCommandService`.

**Presentation**
- Роутер изображений: `/random`, inline vote callbacks, keyboard.
- Команды и тексты для `/set_model`, `/list_models`, `/random`.
- Новый модуль `messages/user.py` (вместо `messages/profile.py`).
- In-chat schedule router: `/schedule`, `add/remove/clear`, `day`, `tz`.

### Changed

**Domain**
- Унифицированы access-ошибки через `kernel.AccessDeniedError` (убраны дубли chat/user).
- Сервисы (model selection/moderation) загружают и сохраняют `User` через `UserRepo`.
- `ModelSelectionPolicy` проверяет effective subscription; `change_settings` и expiry требуют явный fallback-plan.
- Расширены usage/violation порты (`record_usage`, `record_violation`).

**Infrastructure**
- Жизненный цикл SQLAlchemy перенесён в `SQLAUoWFactory` (engine/sessionmaker/metrics/`aclose`), DI закрывает БД через `uow_factory.aclose()`.
- Мониторинг перестроен на VictoriaMetrics + Vector + Loki + Grafana provisioning:
  - Prometheus/promtail и старые celery/frog dashboards удалены.
  - Inline PromQL в runtime dashboard.
  - Алерты только через Grafana provisioning.
- CI job для мониторинга переименован.
- Docker: каталоги `catalog/*.yaml` монтируются read-only (`./catalog:/app/catalog:ro`), без bake в образ; пути задаются через `YAML__MODELS_PATH` и `YAML__SUBSCRIPTIONS_PATH`.

**Application**
- Технологические исключения заменены layer-абстракциями:
  - SQLA* → `DBError` hierarchy.
  - Prometheus*/loguru → `Metrics*` / `logging`.
- Регистрация через domain `UserProfile` / `ChatProfile`, строгие `UserContext` / `ChatContext`.
- `UserCommandsUseCase.select_model` встроен в user command flow.
- Удалены лишние `from __future__ import annotations` в app-слое; docstrings/comments выровнены на английский.

**Presentation**
- `/set_model` переведён на `user_commands_uc`.
- `/random` и vote callbacks переведены на `image_commands_uc`.
- Chat events переорганизованы в `routers/chat` (router/parsers/mappers).
- `/schedule` доступен всем участникам группы; schedule help добавлен в welcome/help.

### Fixed

- После мутирующих chat-команд обновляется Redis snapshot чата (`cache_registry.chat.set`), чтобы исключить устаревший `ChatContext` в последующих update.

### Removed

- `ModelSelectionUseCase`, `ImageRandomUseCase`, `ImageVoteUseCase` (заменены едиными command flows).
- `ImageRandomService` (заменён `ImageCommandService`).
- `messages/profile.py` и связанные тесты профиля (заменены на `messages/user.py` + `tests/.../messages/test_user.py`).
