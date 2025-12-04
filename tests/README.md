# Тесты проекта

## Запуск локально

```bash
pytest -v
```

## Добавление нового теста

- Создайте новый файл в `tests/` согласно структуре модулей проекта.
- Используйте фикстуры из `conftest.py` (`tmp_path`, `monkeypatch`, подготовленные моки клиентов).
- Для асинхронных функций добавляйте декоратор `@pytest.mark.asyncio`.

## Запуск с покрытием

```bash
pytest --cov=bot --cov=services --cov=utils --cov-report=term
pytest --cov=bot --cov=services --cov=utils --cov-report=xml |--cov-report=term-missing
```

## E2E тесты для Celery

E2E тесты для Celery требуют запущенных контейнеров с worker:

```bash
# Запуск тестовых контейнеров (Postgres, Redis, Celery Worker)
make test-up

# Запуск только E2E тестов (pytest сам подождёт готовности worker)
make test-e2e

# Или вручную:
docker compose --env-file .env.test -f docker-compose.test.yml up -d --build
export $(grep -v '^[[:space:]]*#' .env.test | grep -v '^[[:space:]]*$' | xargs) && pytest -m e2e
docker compose -f docker-compose.test.yml down -v
```

**Важно:**
- Используется отдельный тестовый Celery app (`services.celery_app_test`) с тестовыми очередями
- Pytest fixture `celery_worker_ready` автоматически проверяет готовность worker через `test.ping` задачу
- Worker запускается с тестовыми очередями: `test_main`, `test_images`, `test_maintenance`
- Логирование в тестах идёт только в stdout (нет файловых логов)

E2E тесты проверяют:
- Доступность Celery worker через control.inspect()
- Отправку задач в тестовые очереди
- Маршрутизацию задач по очередям
- Мониторинг длины очередей
- Работу result backend (Redis)

## Запуск в CI

Тесты автоматически выполняются при каждом `push` и `pull request` через GitHub Actions.
