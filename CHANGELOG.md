# Changelog

## [7.1.1] — 2026-05-22

### Fixed

**Presentation**
- `AdminAccessFilter`: в `__call__` добавлен аргумент `event: TelegramObject` перед `user: UserContext`. Aiogram передаёт апдейт первым позиционным аргументом; без `event` возникал `TypeError: got multiple values for argument 'user'` на всех `message`, проходящих через `admin_router`.
- Тест: `tests/pres/_aiogram/filters/test_access.py` — вызов фильтра с `event=...`, как в рантайме.

**Monitoring**
- Unit-тест `HighGenerationErrorRate` в `monitoring/prometheus/rules/metrics-rules.test.yml`: удлинены `input_series` и `eval_time: 12m`, чтобы учесть `rate[5m]` и `for: 5m` — стабильный проход `promtool test rules` в CI.
