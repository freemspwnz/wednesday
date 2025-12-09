#!/usr/bin/env bash
set -euo pipefail

# Pytest для unit-набора, без Docker.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
export PYTHONPATH="${REPO_ROOT}"
cd "${REPO_ROOT}"

MARK_EXPR="${MARK_EXPR:-not integration and not db and not redis and not e2e and not infra and not slow}"
PYTEST_XDIST="${PYTEST_XDIST:-}"
COVERAGE_FILE="${COVERAGE_FILE:-.coverage.unit}"
JUNIT_FILE="${JUNIT_FILE:-junit-unitоба.xml}"

export COVERAGE_FILE

pytest \
  tests/ \
  ${PYTEST_XDIST} \
  --cov=bot \
  --cov=services \
  --cov=utils \
  --cov-report=term \
  --cov-report= \
  --cov-fail-under=0 \
  -m "${MARK_EXPR}" \
  --junitxml="${JUNIT_FILE}"

python3 scripts/fix_coverage_paths.py "${COVERAGE_FILE}" 2>/dev/null || true
echo "✓ Unit тесты завершены: ${COVERAGE_FILE}"
