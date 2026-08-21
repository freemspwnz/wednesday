PYTHON ?= python3
UV ?= uv run
IMAGE_NAME := wednesday

PATHS := wednesday/ tests/
COV := --cov=wednesday
TESTS := tests/

.DEFAULT_GOAL := help

CHANGELOG_FILE := CHANGELOG.md

.PHONY: help lint format format-check type test test-cov clean build migrate migrate-revision run changelog-draft

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run ruff lint
	$(UV) ruff check $(PATHS)

format: ## Apply auto-fixes and formatting ruff
	$(UV) ruff check $(PATHS) --fix
	$(UV) ruff format $(PATHS)

format-check: ## Check ruff formatting
	$(UV) ruff format --check $(PATHS)

type: ## Run mypy on all paths and tests
	$(UV) mypy $(PATHS)

test: ## Run all tests
	$(UV) pytest $(TESTS)

test-cov: ## Coverage + junit.xml
	$(UV) pytest $(TESTS) $(COV) --cov-report=term-missing \
		--cov-report=xml:coverage.xml --junitxml=junit.xml

clean: ## Clean temporary artifacts
	rm -rf .pytest_cache .coverage coverage.xml junit.xml .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +

build: ## Build Docker image
	@docker rmi $(IMAGE_NAME):local 2>/dev/null || true
	@docker build -t $(IMAGE_NAME):local .

migrate: ## Apply all Alembic migrations (upgrade head)
	$(UV) alembic upgrade head

migrate-revision: ## Generate migration from ORM diff (MSG=name, needs DB)
	@test -n "$(MSG)" || (echo "Usage: make migrate-revision MSG=describe_change" && exit 1)
	$(UV) alembic revision --autogenerate -m "$(MSG)"

run: ## Run the application
	$(UV) python wednesday/main.py

changelog-draft: ## Draft CHANGELOG since last tag (VERSION=x.y.z; PREPEND=1 writes file)
	@set -euo pipefail; \
	args='--config pyproject.toml --unreleased --offline'; \
	if [ -n "$(VERSION)" ]; then args="$$args --tag $(VERSION)"; fi; \
	if [ "$(PREPEND)" = "1" ]; then \
	  if [ -z "$(VERSION)" ]; then echo "Usage: make changelog-draft VERSION=x.y.z PREPEND=1" >&2; exit 1; fi; \
	  $(UV) git-cliff $$args --prepend $(CHANGELOG_FILE); \
	  echo "Prepended section for $(VERSION) to $(CHANGELOG_FILE) (review before tagging)."; \
	else \
	  $(UV) git-cliff $$args --strip header; \
	fi
