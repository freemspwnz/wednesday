PYTHON := python3
.DEFAULT_GOAL := help

# ============================================================================
# DRY: Переменные для pytest coverage
# ============================================================================
COV_ARGS := --cov=bot --cov=services --cov=utils
COV_REPORT := --cov-report=term --cov-report=
COV_FAIL_UNDER := --cov-fail-under=0

# ============================================================================
# DRY: Переменные для docker compose
# ============================================================================
DOCKER_COMPOSE := docker compose
COMPOSE_PROJECT := wednesday_test
COMPOSE_FILE := tests/docker-compose.test.yml
COMPOSE_ENV := tests/.env.test
COMPOSE_TEST := $(DOCKER_COMPOSE) -p $(COMPOSE_PROJECT) -f $(COMPOSE_FILE) --env-file $(COMPOSE_ENV)
# Корень репозитория на хосте (для исправления путей в coverage)
REPO_ROOT := $(shell pwd)

# ============================================================================
# Переменные для тестов
# ============================================================================
IMAGE_NAME := wednesday-bot
TEST_XDIST ?=1   # По умолчанию включен. Включить: make test-unit TEST_XDIST=0
PYTEST_XDIST := $(shell [ "$(TEST_XDIST)" = "1" ] && echo "-n auto")
TEST_UNIT_MARK_EXPR ?= not integration and not db and not redis and not e2e and not infra and not slow
TEST_INT_MARK_EXPR ?= (integration or db or redis) and not celery and not e2e and not infra and not slow
TEST_E2E_MARK_EXPR ?= e2e and not infra
TEST_INFRA_MARK_EXPR ?= e2e and infra
TEST_SLOW_MARK_EXPR ?= slow
TEST_CELERY_MARK_EXPR ?= celery

.PHONY: help lint format format-check type \
	test-unit test-integration test-e2e test-e2e-infra test-infra \
	test-slow test-celery \
	test-up test-down coverage-merge junit-merge clean ci ci-full build migrate run \
	docs docs-serve docs-build

# ============================================================================
# Help
# ============================================================================

help: ## Показать доступные цели
	@grep -E '^[a-zA-Z0-9_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Линтинг и форматирование
# ============================================================================

lint: ## Запустить ruff lint
	ruff check .

format: ## Применить автоисправления ruff + format
	ruff check . --fix
	ruff format .

format-check: ## Проверить форматирование ruff
	ruff format --check .

type: ## Запустить mypy
	mypy .

# ============================================================================
# Управление тестовыми контейнерами
# ============================================================================

# Запуск тестовых контейнеров (идемпотентный)
# Контейнеры запускаются один раз и переиспользуются всеми тестами
# Lifecycle: start once → reuse → stop once
test-up: ## Поднять тестовые контейнеры
	@COMPOSE_CMD="$(COMPOSE_TEST)" ./scripts/test_up.sh

# Остановка тестовых контейнеров
# Останавливает только тестовый проект, не затрагивает другие контейнеры
test-down: ## Остановить тестовые контейнеры
	@COMPOSE_CMD="$(COMPOSE_TEST)" ./scripts/test_down.sh

# ============================================================================
# Unit тесты (локально, без контейнеров)
# ============================================================================

# Unit тесты запускаются локально без Docker
# Исключают slow/integration/e2e/infra/celery/db/redis маркеры
# Генерируют .coverage.unit и junit-unit.xml
test-unit: ## Unit тесты без контейнеров
	@HOST_REPO_ROOT="$(REPO_ROOT)" PYTEST_XDIST="$(PYTEST_XDIST)" MARK_EXPR="$(TEST_UNIT_MARK_EXPR)" COVERAGE_FILE=".coverage.unit" JUNIT_FILE="junit-unit.xml" ./scripts/pytest_unit.sh

# ============================================================================
# Integration тесты (локально, но подключаются к контейнерам)
# ============================================================================

# Integration тесты запускаются в контейнере `tests`,
# используя сервисы БД/Redis, поднятые через test-up
# Генерируют .coverage.integration и junit-integration.xml
test-integration: ## Integration тесты (внутри docker compose)
	@echo "=== Запуск integration тестов (внутри docker compose) ==="
	@$(COMPOSE_TEST) run --rm \
		-e PYTEST_XDIST="$(PYTEST_XDIST)" \
		-e MARK_EXPR="$(TEST_INT_MARK_EXPR)" \
		-e COVERAGE_FILE=".coverage.integration" \
		-e JUNIT_FILE="junit-integration.xml" \
		-e HOST_REPO_ROOT="$(REPO_ROOT)" \
		tests /app/scripts/pytest_integration.sh

# ============================================================================
# E2E тесты (внутри docker compose)
# ============================================================================

# E2E тесты запускаются внутри docker compose run tests
# Требуют запущенных контейнеров (test-up) и выполненных миграций (migrate)
# Контейнеры НЕ перезапускаются здесь (переиспользуются)
# Генерируют .coverage.e2e и junit-e2e.xml
test-e2e: ## E2E тесты без infra
	@echo "=== Запуск E2E тестов (внутри docker compose) ==="
	@$(COMPOSE_TEST) run --rm \
		-e PYTEST_XDIST="$(PYTEST_XDIST)" \
		-e MARK_EXPR="$(TEST_E2E_MARK_EXPR)" \
		-e COVERAGE_FILE=".coverage.e2e" \
		-e JUNIT_FILE="junit-e2e.xml" \
		-e HOST_REPO_ROOT="$(REPO_ROOT)" \
		tests /app/scripts/pytest_e2e.sh

# ============================================================================
# E2E infra тесты (внутри docker compose)
# ============================================================================

# E2E infra тесты запускаются внутри docker compose run tests
# Используют те же контейнеры, что и обычные E2E тесты
# Генерируют .coverage.infra и junit-e2e-infra.xml
# Используют отдельный файл покрытия (можно объединить с e2e через coverage combine)
test-e2e-infra: ## E2E тесты infra
	@echo "=== Запуск E2E infra тестов (внутри docker compose) ==="
	@$(COMPOSE_TEST) run --rm \
		-e PYTEST_XDIST="$(PYTEST_XDIST)" \
		-e MARK_EXPR="$(TEST_INFRA_MARK_EXPR)" \
		-e COVERAGE_FILE=".coverage.infra" \
		-e JUNIT_FILE="junit-e2e-infra.xml" \
		-e HOST_REPO_ROOT="$(REPO_ROOT)" \
		tests /app/scripts/pytest_infra.sh

test-infra: test-e2e-infra ## Алиас для infra тестов

# ============================================================================
# Slow тесты (долгие тесты)
# ============================================================================

# Slow тесты запускаются в контейнере `tests`,
# так как некоторые из них требуют БД (например, test_image_generator.py)
# Генерируют .coverage.slow и junit-slow.xml
test-slow: ## Slow тесты (внутри docker compose)
	@echo "=== Запуск Slow тестов (внутри docker compose) ==="
	@$(COMPOSE_TEST) run --rm \
		-e PYTEST_XDIST="$(PYTEST_XDIST)" \
		-e MARK_EXPR="$(TEST_SLOW_MARK_EXPR)" \
		-e COVERAGE_FILE=".coverage.slow" \
		-e JUNIT_FILE="junit-slow.xml" \
		-e HOST_REPO_ROOT="$(REPO_ROOT)" \
		tests /app/scripts/pytest_slow.sh

# ============================================================================
# Celery тесты
# ============================================================================

# Celery тесты запускаются в контейнере `tests`,
# используя сервисы Postgres/Redis/Celery worker, поднятые через test-up
# Генерируют .coverage.celery и junit-celery.xml
test-celery: ## Celery тесты (внутри docker compose)
	@echo "=== Запуск Celery тестов (внутри docker compose) ==="
	@$(COMPOSE_TEST) run --rm \
		-e PYTEST_XDIST="$(PYTEST_XDIST)" \
		-e MARK_EXPR="$(TEST_CELERY_MARK_EXPR)" \
		-e COVERAGE_FILE=".coverage.celery" \
		-e JUNIT_FILE="junit-celery.xml" \
		-e HOST_REPO_ROOT="$(REPO_ROOT)" \
		tests /app/scripts/pytest_celery.sh

# ============================================================================
# Объединение покрытия кода
# ============================================================================

# Объединяет покрытие из всех фаз тестирования
# Coverage strategy: отдельные файлы на каждую фазу → merge в конце
coverage-merge: ## Объединить все coverage файлы
	@echo "=== Объединение покрытия кода из всех фаз ==="
	@if ls .coverage.* 1>/dev/null 2>&1; then \
		for f in $(wildcard .coverage.*); do \
			echo "Исправление путей в $$f"; \
			HOST_REPO_ROOT="$(REPO_ROOT)" $(PYTHON) scripts/fix_coverage_paths.py "$$f" || true; \
		done; \
		coverage combine $(wildcard .coverage.*) || true; \
	else \
		echo "⚠ Предупреждение: файлы покрытия не найдены"; \
	fi
	@coverage xml -o coverage.xml --ignore-errors || true
	@coverage report --fail-under=50 --ignore-errors || true
	@echo "✓ Покрытие объединено в coverage.xml"

junit-merge: ## Объединить все JUnit XML файлы
	@echo "=== Объединение JUnit XML файлов ==="
	@HOST_REPO_ROOT="$(REPO_ROOT)" $(PYTHON) scripts/merge_junit.py junit.xml

# ============================================================================
# Очистка
# ============================================================================

# Очистка временных файлов покрытия (опционально)
# Можно использовать для отладки или полной очистки перед новым запуском
clean: ## Очистить временные файлы
	@echo "=== Очистка временных файлов ==="
	@rm -f .coverage .coverage.* coverage.xml junit*.xml .ci_failed
	@echo "✓ Очистка завершена"

# ============================================================================
# Миграции
# ============================================================================

# Прогон миграций/инициализации схемы БД
# Используется локально и в CI перед запуском тестов, требующих БД
# Требует запущенных контейнеров (test-up)
migrate: ## Прогнать миграции для тестов (в контейнере tests)
	@echo "=== Прогон миграций (инициализация схемы Postgres) ==="
	@$(COMPOSE_TEST) run --rm \
		tests $(PYTHON) -m tests.helpers.postgres_schema
	@echo "✓ Миграции выполнены"

# ============================================================================
# CI Pipeline
# ============================================================================

# Полный CI pipeline с единым жизненным циклом контейнеров
# Container lifecycle: start once → reuse → stop once
# Coverage strategy: отдельные файлы на каждую фазу → merge в конце
ci: ## Полный CI пайплайн (быстрые тесты, 209 тестов)
	@set -e; \
	trap 'COMPOSE_CMD="$(COMPOSE_TEST)" $(MAKE) test-down >/dev/null' EXIT; \
	echo "=== Линтинг и проверка форматирования ==="; \
	$(MAKE) lint; \
	$(MAKE) format-check; \
	$(MAKE) type; \
	echo "=== Сборка документации MkDocs ==="; \
	$(MAKE) docs-build; \
	echo "=== Unit тесты (локально, без контейнеров) ==="; \
	$(MAKE) test-unit; \
	echo "=== Запуск тестовых контейнеров (один раз) ==="; \
	COMPOSE_CMD="$(COMPOSE_TEST)" $(MAKE) test-up; \
	echo "=== Миграции ==="; \
	$(MAKE) migrate; \
	echo "=== Integration тесты (внутри docker compose) ==="; \
	$(MAKE) test-integration; \
	echo "=== E2E тесты (внутри docker compose) ==="; \
	$(MAKE) test-e2e; \
	echo "=== E2E infra тесты (внутри docker compose) ==="; \
	$(MAKE) test-e2e-infra; \
	echo "=== Объединение покрытия кода ==="; \
	$(MAKE) coverage-merge; \
	echo "=== Объединение JUnit XML ==="; \
	$(MAKE) junit-merge; \
	trap - EXIT; \
	COMPOSE_CMD="$(COMPOSE_TEST)" $(MAKE) test-down; \
	echo "✓ CI pipeline завершён успешно"

ci-full: ## Полный CI пайплайн со всеми тестами (231 тест, включая slow и celery)
	@set -e; \
	trap 'COMPOSE_CMD="$(COMPOSE_TEST)" $(MAKE) test-down >/dev/null' EXIT; \
	echo "=== Линтинг и проверка форматирования ==="; \
	$(MAKE) lint; \
	$(MAKE) format-check; \
	$(MAKE) type; \
	echo "=== Сборка документации MkDocs ==="; \
	$(MAKE) docs-build; \
	echo "=== Unit тесты (локально, без контейнеров) ==="; \
	$(MAKE) test-unit; \
	echo "=== Запуск тестовых контейнеров (один раз) ==="; \
	COMPOSE_CMD="$(COMPOSE_TEST)" $(MAKE) test-up; \
	echo "=== Миграции ==="; \
	$(MAKE) migrate; \
	echo "=== Slow тесты (внутри docker compose) ==="; \
	$(MAKE) test-slow; \
	echo "=== Integration тесты (внутри docker compose) ==="; \
	$(MAKE) test-integration; \
	echo "=== Celery тесты (внутри docker compose) ==="; \
	$(MAKE) test-celery; \
	echo "=== E2E тесты (внутри docker compose) ==="; \
	$(MAKE) test-e2e; \
	echo "=== E2E infra тесты (внутри docker compose) ==="; \
	$(MAKE) test-e2e-infra; \
	echo "=== Объединение покрытия кода ==="; \
	$(MAKE) coverage-merge; \
	echo "=== Объединение JUnit XML ==="; \
	$(MAKE) junit-merge; \
	trap - EXIT; \
	COMPOSE_CMD="$(COMPOSE_TEST)" $(MAKE) test-down; \
	echo "✓ CI pipeline (полный) завершён успешно"

# ============================================================================
# Сборка и запуск
# ============================================================================

# Сборка Docker-образа бота (с очисткой старого)
build: ## Собрать Docker-образ бота
	@echo "Очистка старого образа $(IMAGE_NAME):local..."
	@docker rmi $(IMAGE_NAME):local 2>/dev/null || true
	@echo "Сборка нового образа $(IMAGE_NAME):local..."
	@docker build -t $(IMAGE_NAME):local .
	@echo "✓ Образ собран успешно"

# Запуск бота в Docker-контейнерах (с пересборкой образа)
run: ## Запустить бота в Docker-контейнерах
	@./scripts/docker_run_bot.sh

# ============================================================================
# Документация MkDocs
# ============================================================================

# Локальный сервер для просмотра документации
docs-serve: ## Запустить локальный сервер MkDocs (http://127.0.0.1:8000)
	@echo "=== Запуск локального сервера MkDocs ==="
	@SITE_URL="" mkdocs serve
	@echo "✓ Сервер остановлен"

# Сборка статической документации
docs-build: ## Собрать статическую документацию MkDocs в директорию site/
	@echo "=== Сборка документации MkDocs ==="
	@SITE_URL="https://github.com/Freemspwnz/wednesday" mkdocs build
	@echo "✓ Документация собрана в директорию site/"

# Алиас для сборки документации
docs: docs-build ## Алиас для docs-build
