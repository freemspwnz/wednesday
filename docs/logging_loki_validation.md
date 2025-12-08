Валидация и поэтапное внедрение Loki/Grafana/Promtail
=====================================================

Этот документ описывает практические шаги проверки стека логирования (Promtail → Loki → Grafana)
и рекомендации по поэтапному внедрению (dev → stage → prod).

## 1. Базовая проверка стека

1. Собрать образ бота:

   ```bash
   make build
   ```

2. Поднять инфраструктуру логирования и приложение в dev:

   ```bash
   docker compose up -d postgres redis
   docker compose up -d loki grafana promtail
   docker compose up -d bot
   ```

3. Проверить healthcheck-и:

   - `docker compose ps` — сервисы `loki`, `grafana`, `promtail`, `wednesday_bot` должны быть `running/healthy`;
   - `curl http://localhost:3100/ready` — Loki готов;
   - `curl http://localhost:9080/metrics` — Promtail отдаёт метрики;
   - `curl http://localhost:8080/health` — healthcheck приложения.

4. Открыть Grafana:

   - URL: `http://localhost:3000`
   - Логин/пароль по умолчанию: `admin` / `admin`
   - Убедиться, что:
     - datasource `Loki` создан и работает;
     - dashboard `Wednesday Bot Logs` доступен и показывает данные.

## 2. Проверка схемы логов и полей

1. В Grafana (Explore → Loki) выполнить запрос:

   ```logql
   {job="wednesday-json-logs"}
   ```

2. Убедиться, что:

   - видны labels: `env`, `service`, `level`, `event`, `status`;
   - сырые записи содержат поля `time`, `level`, `message` и `extra.*`;
   - timestamp соответствует времени генерации событий.

3. Проверить наличие ключевых полей:

   - `user_id`, `prompt_hash`, `latency_ms`, `image_id` (как поля для поиска, а не labels);
   - выполнить поисковые запросы вида:

     ```logql
     {event="generation"} | json | latency_ms > 0
     ```

## 3. Проверка дашборда

1. Открыть дашборд `Wednesday Bot Logs`.
2. Проверить панели:

   - **Log rate by level** — корректно считает количество записей по уровням;
   - **Events by type** — распределение событий по `event`;
   - **Latency (ms) for generation** — отображает 95‑й перцентиль по `latency_ms` для `event="generation"`;
   - **Recent logs** — показывает последние логи с фильтрацией по `env`, `service`, `level`, `event`, `status`.

3. Вручную изменить фильтры (`env`, `service`, `event`, `status`) и убедиться, что данные корректно фильтруются.

## 4. Проверка alerting

1. Включить rule group `wednesday-logging` в Grafana (Alerting → Alert rules).
2. Для правила `High error rate in logs`:

   - сгенерировать серию ошибок в приложении (например, вызвать заведомо невалидную команду или форсировать ошибки HTTP‑клиентов);
   - убедиться, что при достижении порога алёрт срабатывает (для dev достаточно проверить состояние правила и test firing).

3. Для правила `Suspicious secret patterns in logs`:

   - в dev окружении временно сгенерировать тестовые сообщения, содержащие строки `Authorization`/`Bearer`/`BEGIN_PRIVATE_KEY` (без реальных секретов);
   - убедиться, что правило срабатывает даже на единичное событие.

## 5. Отказоустойчивость и деградация

1. Остановить Loki:

   ```bash
   docker compose stop loki
   ```

2. Проверить:

   - приложение продолжает писать логи в `logs/wednesday_bot.log` и `logs/wednesday_bot.events.jsonl`;
   - Promtail показывает ошибки доставки, но не влияет на работу бота;
   - healthcheck приложения `/health` остаётся зелёным.

3. Аналогично проверить недоступность Promtail:

   ```bash
   docker compose stop promtail
   ```

4. Убедиться, что:

   - приложение продолжает работать;
   - после повторного запуска Promtail догоняет новые записи из файлов.

## 6. Проверка отсутствия секретов

1. Сгенерировать тестовые события, которые в коде **до** маскировки содержали бы:

   - `GIGACHAT_AUTHORIZATION_KEY`;
   - различные `access_token`/`refresh_token`/`password` в `extra`.

2. Проверить по файлу `logs/wednesday_bot.events.jsonl` (локально) и через Loki:

   - прямым текстовым поиском в файле (например, `grep` по известным значениям ключей);
   - поиском по LogQL в Grafana:

     ```logql
     {job="wednesday-json-logs"} |= "GIGACHAT_AUTHORIZATION_KEY"
     ```

3. Убедиться, что:

   - секретные значения нигде не встречаются;
   - вместо них используются `"****"` или безопасные превью.

## 7. Переход dev → stage → prod

Рекомендуемая последовательность:

1. **dev**:
   - полностью обкатать сбор логов, дашборды и алёрты;
   - при необходимости скорректировать labels/правила alerting, пороги и панели.
2. **stage**:
   - развернуть аналогичный стек (с отдельным Loki/Grafana или tenant’ом);
   - включить alerting, в том числе по подозрительным паттернам;
   - проверить поведение под более высокой нагрузкой.
3. **prod**:

   - использовать либо:
     - отдельный Loki/Grafana кластер (k8s/отдельный хост);
     - либо управляемый Loki (S3 backend, внешние диски и т.п.);
   - придерживаться тех же принципов:
     - labels ограничены `service`, `env`, `level`, `event`, `status`;
     - `user_id`, `prompt_hash` и другие высококардинальные поля остаются полями поиска;
   - продуманно настроить retention (по времени/объёму) в зависимости от требований.

4. При необходимости можно рассмотреть дополнительный HTTP‑sink в Loki из приложения,
   но только:

   - с отдельным буфером/очередью и ретраями;
   - без блокировки критического пути логирования;
   - с явной возможностью деградации до файловых логов при недоступности Loki.
