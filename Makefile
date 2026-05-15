PYTHON ?= python3
POETRY ?= poetry run
IMAGE_NAME := wednesday

PATHS := wednesday/domain/ wednesday/app/ wednesday/infra/ tests/
COV := --cov=domain --cov=app --cov=infra
TESTS := tests/

.DEFAULT_GOAL := help

.PHONY: help lint format format-check type test test-cov clean build

help: ## Показать доступные цели
	@grep -E '^[a-zA-Z0-9_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Запустить ruff lint
	$(POETRY) ruff check $(PATHS)

format: ## Применить автоисправления и форматирование ruff
	$(POETRY) ruff check $(PATHS) --fix
	$(POETRY) ruff format $(PATHS)

format-check: ## Проверить форматирование ruff
	$(POETRY) ruff format --check $(PATHS)

type: ## Запустить mypy по всем путям и тестам
	$(POETRY) mypy $(PATHS)

test: ## Запустить все тесты с покрытием
	$(POETRY) pytest --cov=wednesday --cov-report=term-missing --cov-report=xml:coverage.xml

test-cov: ## coverage + junit.xml
	$(POETRY) pytest $(TESTS) $(COV) --cov-report=term-missing \
		--cov-report=xml:coverage.xml --junitxml=junit.xml

clean: ## Очистить временные артефакты
	rm -rf .pytest_cache .coverage coverage.xml junit.xml .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +

build: ## Собрать Docker-образ бота
	@docker rmi $(IMAGE_NAME):local 2>/dev/null || true
	@docker build -t $(IMAGE_NAME):local .
