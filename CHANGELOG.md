# Changelog

## [7.7.0] — 2026-08-21

### Added

**Domain**
- `ViewRepo.reset_for_chat`: clear all view rows for a chat and return the deleted count ([#50](https://github.com/freemspwnz/wednesday/issues/50)).

**App**
- Image generation resolves a `Generator` per vendor via `GeneratorRegistry`; unknown vendors map to `GENERATION_FAILED` for the user ([#43](https://github.com/freemspwnz/wednesday/issues/43)).
- `ImageCatalogUseCase.reset_views` clears a chat's viewed-image history for `/random` reuse ([#50](https://github.com/freemspwnz/wednesday/issues/50)).

**Presentation**
- `/schedule` is a full inline menu in groups: day, timezone, broadcast on/off, slot add/remove/clear, and Close. Typed `schedule_*` commands are removed; `/schedule` is in help and BotCommand ([#66](https://github.com/freemspwnz/wednesday/issues/66)).
- `/reset` confirms via inline buttons, then clears the chat's catalog view history so `/random` can show previously seen images again; the empty-state hint mentions `/reset` ([#50](https://github.com/freemspwnz/wednesday/issues/50)).
- `/models` opens an inline picker of models allowed for the user's tier; success reuses the same confirmation as `/set_model`. Legacy `/set_model` / `/list_models` remain as power-user paths but are omitted from help and BotCommand ([#75](https://github.com/freemspwnz/wednesday/issues/75)).

**Infrastructure**
- `ProvidersRegistry` implements `GeneratorRegistry`: vendor lookup returns the cached Sber client; unknown vendors fail without opening HTTP ([#43](https://github.com/freemspwnz/wednesday/issues/43)).

### Changed

**Domain**
- `User.unban` is a noop when already active (no error, no `updated_at` bump); unused `UserNotBannedError` removed ([#80](https://github.com/freemspwnz/wednesday/issues/80)).
- ID value objects normalized; domain helper factories removed so adapters stop depending on convenience APIs ([#69](https://github.com/freemspwnz/wednesday/issues/69)).

**App**
- User/chat/image use cases take primitives and return context/read-model DTOs; handlers no longer build domain VOs ([#69](https://github.com/freemspwnz/wednesday/issues/69)).
- Cache ports store flattened context DTOs instead of domain aggregates ([#69](https://github.com/freemspwnz/wednesday/issues/69)).
- Image generation orchestration lives in one `generate(prompt)` entry point (routing, moderation, ID creation); quota/ban stay in the handler ([#64](https://github.com/freemspwnz/wednesday/issues/64)).

**Presentation**
- Group routing uses Telegram chat type from the update, not `ChatContext.type` ([#66](https://github.com/freemspwnz/wednesday/issues/66)).
- Schedule router split into actions and screens; handlers pass primitives and consume app DTOs only ([#66](https://github.com/freemspwnz/wednesday/issues/66), [#69](https://github.com/freemspwnz/wednesday/issues/69)).

**Infrastructure**
- Redis persists `UserContext` / `ChatContext` via a versioned JSON codec instead of mirrored pydantic snapshots ([#76](https://github.com/freemspwnz/wednesday/issues/76)).
- Shared `guard_view` helper for `ViewRepo` SQLAlchemy error mapping ([#50](https://github.com/freemspwnz/wednesday/issues/50)).

### Fixed

**App**
- Concurrent `/generate` could pass limit checks before usage was recorded; `begin_generation` now locks, checks, and consumes in one UoW, with refund on failed render/send ([#49](https://github.com/freemspwnz/wednesday/issues/49)).

**Presentation**
- Catalog schedule runner no longer reuses process-start time; due scans and sleep advance each minute ([#77](https://github.com/freemspwnz/wednesday/issues/77)).
- Schedule callbacks ack before slow work, restore limit/duplicate toasts, and skip no-op markup edits that triggered Telegram flood waits ([#66](https://github.com/freemspwnz/wednesday/issues/66)).

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
