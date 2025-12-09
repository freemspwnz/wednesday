#!/usr/bin/env bash
set -euo pipefail

# Pytest для integration внутри контейнера tests.
MARK_EXPR="${MARK_EXPR:-(integration or db or redis) and not celery and not e2e and not infra and not slow}"
COVERAGE_FILE="${COVERAGE_FILE:-.coverage.integration}"
JUNIT_FILE="${JUNIT_FILE:-junit-integration.xml}"
PYTEST_XDIST="${PYTEST_XDIST:-}"

export COVERAGE_FILE

cd /app
export PYTHONPATH=/app

pytest \
  ${PYTEST_XDIST} \
  --cov=bot \
  --cov=services \
  --cov=utils \
  --cov-report=term \
  --cov-report= \
  --cov-fail-under=0 \
  -m "${MARK_EXPR}" \
  --junitxml="${JUNIT_FILE}"

# Финализируем coverage для закрытия SQLite WAL и синхронизации через volume
# coverage xml заставляет SQLite полностью закрыть транзакции и WAL
python3 -m coverage xml -o /dev/null 2>/dev/null || true

python3 scripts/fix_coverage_paths.py "${COVERAGE_FILE}" 2>/dev/null || true
echo "✓ Integration тесты завершены: ${COVERAGE_FILE}"
