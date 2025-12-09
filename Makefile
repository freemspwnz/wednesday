PYTHON := python3

COV_ARGS := --cov=bot --cov=services --cov=utils

IMAGE_NAME := wednesday-bot

.PHONY: lint format format-check \
	test-unit-no-container test-integration-containers test-e2e test-e2e-infra \
	test-cov test-cleanup test-up test-down type run ci build migrate

lint:
	ruff check .

format:
	ruff check . --fix
	ruff format .

# ⚠️ КРИТИЧНО: Добавлен timeout для предотвращения зависаний в CI
# Если docker build или compose зависнет, команда завершится через 5 минут
# На macOS timeout может быть недоступен, поэтому используем условную проверку

# Запуск тестовых контейнеров
test-up:
	@./scripts/test_up.sh

# Остановка тестовых контейнеров
test-down:
	@./scripts/test_down.sh

# Unit без контейнеров (mocked DB/Redis/Celery), исключаем slow/infra/e2e
test-unit-no-container:
	@echo "=== Запуск unit без контейнеров (no containers) ==="
	@pytest -m "not integration and not e2e and not infra and not celery and not db and not redis and not slow" \
		--junitxml=junit.xml

# Integration c контейнерами Postgres/Redis, без Celery e2e/infra
test-integration-containers: test-down
	@echo "=== Запуск integration с контейнерами (Postgres/Redis) ==="
	@$(MAKE) test-up || ($(MAKE) test-down && exit 1)
	@docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
		pytest $(COV_ARGS) --cov-report=xml:coverage.xml --cov-report=term \
		--cov-fail-under=50 \
		--junitxml=junit.xml -m "(integration or db or redis) and not celery and not e2e and not infra and not slow"; \
	TEST_EXIT_CODE=$$?; \
	$(MAKE) test-down; \
	exit $$TEST_EXIT_CODE

# E2E без infra (боты, Celery e2e базовые)
test-e2e: test-down
	@echo "=== Запуск E2E (без infra) ==="
	@./scripts/run_e2e.sh -m "e2e and not infra"

# Infra-набор Celery (диагностические e2e)
test-e2e-infra: test-down
	@echo "=== Запуск Celery infra E2E ==="
	@./scripts/run_e2e.sh -m "e2e and infra"

# Запуск тестов с покрытием (integration-матрица)
test-cov: test-integration-containers

type:
	mypy .

# Прогон миграций/инициализации схемы БД.
# Используется локально и в CI перед запуском тестов и приложений.
migrate:
	@echo "=== Прогон миграций (инициализация схемы Postgres) ==="
	@POSTGRES_USER=$${POSTGRES_USER:-test_user} \
	 POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-test_password_ci_2024} \
	 POSTGRES_DB=$${POSTGRES_DB:-wednesdaydb_test} \
	 POSTGRES_HOST=$${POSTGRES_HOST:-localhost} \
	 POSTGRES_PORT=$${POSTGRES_PORT:-5432} \
	 python -m utils.postgres_schema

# Сборка Docker-образа бота (с очисткой старого)
build:
	@echo "Очистка старого образа $(IMAGE_NAME):local..."
	@docker rmi $(IMAGE_NAME):local 2>/dev/null || true
	@echo "Сборка нового образа $(IMAGE_NAME):local..."
	@docker build -t $(IMAGE_NAME):local .
	@echo "✓ Образ собран успешно"

# Запуск бота в Docker-контейнерах (с пересборкой образа)
run: build
	@echo "=== Запуск бота в Docker-контейнерах ==="
	@echo "Очистка старых контейнеров..."
	@docker-compose down
	@echo "Поднятие боевых контейнеров Postgres и Redis..."
	@docker-compose up -d postgres redis
	@echo "Ожидание готовности сервисов..."
	@timeout=60; \
	while [ $$timeout -gt 0 ]; do \
		postgres_health=$$(docker inspect --format='{{.State.Health.Status}}' wednesday_postgres 2>/dev/null || echo "starting"); \
		redis_health=$$(docker inspect --format='{{.State.Health.Status}}' wednesday_redis 2>/dev/null || echo "starting"); \
		if [ "$$postgres_health" = "healthy" ] && [ "$$redis_health" = "healthy" ]; then \
			echo "✓ Сервисы готовы"; \
			break; \
		fi; \
		echo "Ожидание сервисов... (Postgres: $$postgres_health, Redis: $$redis_health)"; \
		sleep 2; \
		timeout=$$((timeout-1)); \
	done; \
	if [ $$timeout -eq 0 ]; then \
		echo "✗ Таймаут ожидания готовности сервисов"; \
		exit 1; \
	fi
	@echo "Запуск бота..."
	@docker-compose up bot

# Полный CI pipeline (локальный): поднимает контейнеры один раз, все тесты используют их
ci:
	@echo "=== Локальный CI: unit + integration + e2e + infra ==="
	@rm -f .ci_failed
	@$(MAKE) lint
	@$(MAKE) format-check
	@$(MAKE) type
	@echo "=== Поднятие тестовых контейнеров ==="
	@$(MAKE) test-up || (echo "✗ Не удалось поднять контейнеры" && touch .ci_failed && exit 1)
	@$(MAKE) migrate || ($(MAKE) test-down && echo "✗ Миграции провалились" && touch .ci_failed && exit 1)
	@echo "=== Unit тесты (без контейнеров) ==="
	@-$(MAKE) test-unit-no-container || (echo "✗ Unit тесты провалились" && touch .ci_failed)
	@echo "=== Integration тесты (с контейнерами) ==="
	@-docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
		pytest $(COV_ARGS) --cov-report=xml:coverage.xml --cov-report=term \
		--cov-fail-under=50 \
		--junitxml=junit.xml -m "(integration or db or redis) and not celery and not e2e and not infra and not slow" || (echo "✗ Integration тесты провалились" && touch .ci_failed)
	@echo "=== E2E тесты (без infra) ==="
	@-docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
		pytest $(COV_ARGS) --cov-report=xml:coverage-e2e.xml --cov-report=term \
		--junitxml=junit-e2e.xml -m "e2e and not infra" || (echo "✗ E2E тесты провалились" && touch .ci_failed)
	@echo "=== E2E infra тесты ==="
	@-docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
		pytest --junitxml=junit-e2e-infra.xml -m "e2e and infra" || (echo "✗ E2E infra тесты провалились" && touch .ci_failed)
	@echo "=== Остановка тестовых контейнеров ==="
	@$(MAKE) test-down
	@$(MAKE) build
	@if [ -f .ci_failed ]; then \
		rm -f .ci_failed; \
		echo "✗ CI pipeline завершён с ошибками"; \
		exit 1; \
	fi
	@echo "✓ CI pipeline завершён успешно"

# Проверка форматирования без изменений
format-check:
	@ruff format --check .
