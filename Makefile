PYTHON := python3

COV_ARGS := --cov=bot --cov=services --cov=utils

IMAGE_NAME := wednesday-bot

.PHONY: lint format format-check test test-cov test-no-containers test-cleanup test-up test-down test-e2e type run ci build migrate

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

# Запуск unit/integration тестов
test: test-down
	@echo "=== Запуск Unit/Integration тестов ==="
	@$(MAKE) test-up || ($(MAKE) test-down && exit 1)
	@docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
		pytest --junitxml=junit.xml -m "not e2e"; \
	TEST_EXIT_CODE=$$?; \
	$(MAKE) test-down; \
	exit $$TEST_EXIT_CODE

# Запуск тестов с покрытием (coverage.xml + junit.xml)
test-cov: test-down
	@echo "=== Запуск тестов с тестовыми контейнерами (с покрытием) ==="
	@$(MAKE) test-up || ($(MAKE) test-down && exit 1)
	@docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
		pytest $(COV_ARGS) --cov-report=xml:coverage.xml --cov-report=term \
		--junitxml=junit.xml -m "not e2e"; \
	TEST_EXIT_CODE=$$?; \
	$(MAKE) test-down; \
	exit $$TEST_EXIT_CODE

# Запуск тестов без контейнеров (предполагает, что БД уже запущены)
test-no-containers:
	@echo "=== Запуск тестов без запуска контейнеров ==="
	@pytest $(COV_ARGS) --cov-report=xml:coverage.xml --cov-report=term \
		--junitxml=junit.xml \
		-o junit_family=legacy

# Запуск E2E тестов
test-e2e: test-down
	@echo "=== Запуск E2E тестов ==="
	@./scripts/run_e2e.sh

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

# Полный CI pipeline (lint, format check, type check, tests with coverage)
ci:
	@echo "=== Запуск полного CI pipeline ==="
	@$(MAKE) lint
	@$(MAKE) type
	@$(MAKE) migrate
	@$(MAKE) test-cov
	@$(MAKE) build

# Проверка форматирования без изменений
format-check:
	@ruff format --check .
