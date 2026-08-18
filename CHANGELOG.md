# Changelog

## [7.6.0] — 2026-08-18

### Added

**Domain**
- `ChatScheduleSet` / `Chat.is_due_at`: слот due по локальному weekday и hour:minute чата; пустой и inactive чат не due.

**App**
- Список чатов с due-слотом: `ChatRepo` отдаёт активные чаты со слотами, use case фильтрует по `is_due_at`. CRUD и cache snapshots без изменений.
- INFO-логи исходов, которые handler wrapper не видит: generate finish, `assign_ban`, первая регистрация user/chat. Cache и scenario-start остаются на DEBUG.

**Presentation**
- `CatalogScheduleRunner` раз в минуту шлёт фото из каталога в чаты с due-слотом (`pick_for_chat` + `send_photo`, без GigaChat). CRUD команд расписания без изменений.
- `_run_handler` пишет structured INFO-breadcrumb (command/callback, user/chat ids) до `action()`.
- `/generate`: `PromptRejectedError` логируется WARNING до `assign_ban` — moderation events видны в Loki.

**Infrastructure**
- GigaChat text completions передают `temperature=0.9` / `top_p=0.95` (`SberClient` ClassVars); image payload и `GigaChatConfig` без изменений.
- GigaChat adapter: start/finish генерации на INFO, slot-busy timeout на WARNING.
- Rate-limiter и circuit breaker: structured WARNING перед reject (429 / circuit open).
- SQLAlchemy engine: runtime query errors на WARNING (`command`, `error_type`), без SQL text в kwargs.
- HttpClient: timeout, transport, 429, circuit open и exhausted retries — structured WARNING/ERROR без request body.

### Changed

**App**
- I/O-оркестрация user/chat/image (load/save, lookup, vote, schedule, generation, strike) перенесена из domain-сервисов в application use cases с явными границами UoW. Domain остаётся sync aggregates и policies.

### Fixed

**App**
- Голос 👍/👎 помечает картинку shown для лички голосующего (`chat_id_from_tg(user.tg_id)`), чтобы `/random` в PM не отдавал уже оценённое в группе.

**Presentation**
- Throttle колбэков (👍/👎) больше не пишет шутку в чат: кликнувший получает персональный toast, спиннер не зависает. Флуд команд по-прежнему предупреждается сообщением.
- Due-слот с пустым каталогом шлёт notice `/generate` вместо silent skip; `mark_shown` только после успешного send. CRUD расписания и GigaChat не на этом пути.

**Infrastructure**
- Retrier: исчерпание попыток и unexpected errors — отдельные WARNING с `error_type` (раньше терялись на DEBUG).
