PYTHON ?= python3
POETRY ?= poetry run
IMAGE_NAME := wednesday-bot

DOMAIN_PATHS := wednesday/domain/user wednesday/domain/kernel tests/domain/user tests/domain/kernel
DOMAIN_TESTS := tests/domain/user tests/domain/kernel
DOMAIN_COV := --cov=wednesday/domain/user --cov=wednesday/domain/kernel

.DEFAULT_GOAL := help

.PHONY: help lint format format-check type type-domain test test-domain test-cov clean build run

help: ## Показать доступные цели
	@grep -E '^[a-zA-Z0-9_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Запустить ruff lint
	$(POETRY) ruff check .

format: ## Применить автоисправления и форматирование ruff
	$(POETRY) ruff check . --fix
	$(POETRY) ruff format .

format-check: ## Проверить форматирование ruff
	$(POETRY) ruff format --check .

type: ## Запустить mypy на всем проекте
	$(POETRY) mypy .

type-domain: ## Запустить mypy только для domain user+kernel
	$(POETRY) mypy $(DOMAIN_PATHS)

test: ## Запустить все тесты с покрытием
	$(POETRY) pytest --cov=wednesday --cov-report=term-missing --cov-report=xml:coverage.xml

test-domain: ## Запустить только domain тесты
	$(POETRY) pytest $(DOMAIN_TESTS)

test-cov: ## Запустить domain quality gate (pre-push)
	$(POETRY) pytest $(DOMAIN_TESTS) $(DOMAIN_COV) --cov-report=term-missing --cov-report=xml:coverage.xml

clean: ## Очистить временные артефакты
	rm -rf .pytest_cache .coverage coverage.xml .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +

build: ## Собрать Docker-образ бота
	@docker rmi $(IMAGE_NAME):local 2>/dev/null || true
	@docker build -t $(IMAGE_NAME):local .

run: ## Запустить бота в Docker-контейнерах
	@./scripts/docker_run_bot.sh
