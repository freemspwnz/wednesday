#!/usr/bin/env bash
set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${THIS_DIR}/.."

cd "${REPO_ROOT}"

MARK_EXPR="${1:-e2e and not infra}"
PYTEST_E2E_ARGS=${PYTEST_E2E_ARGS:-}

"${THIS_DIR}/test_up.sh"

set +e
docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
  pytest \
    --cov=bot \
    --cov=services \
    --cov=utils \
    --cov-report=xml:coverage-e2e.xml \
    --cov-report=term \
    --junitxml=junit-e2e.xml \
    -m "${MARK_EXPR}" \
    ${PYTEST_E2E_ARGS}
TEST_EXIT_CODE=$?
set -e

"${THIS_DIR}/test_down.sh"

exit "${TEST_EXIT_CODE}"
