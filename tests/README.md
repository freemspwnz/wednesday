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

E2E тесты для Celery требуют запущенных контейнеров с worker и beat:

```bash
# Запуск тестовых контейнеров (включая celery-worker-test и celery-beat-test)
docker-compose -f docker-compose.test.yml up -d

# Дождаться готовности всех сервисов
docker-compose -f docker-compose.test.yml ps

# Запуск только E2E тестов
pytest tests/test_services/test_celery_e2e.py -v -m e2e

# Остановка контейнеров
docker-compose -f docker-compose.test.yml down
```

E2E тесты проверяют:
- Доступность Celery worker через control.inspect()
- Отправку задач в очереди
- Маршрутизацию задач по очередям
- Регистрацию расписания в Celery Beat
- Мониторинг длины очередей
- Работу result backend (Redis)

## Запуск в CI

Тесты автоматически выполняются при каждом `push` и `pull request` через GitHub Actions.
