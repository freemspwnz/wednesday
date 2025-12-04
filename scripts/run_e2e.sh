#!/usr/bin/env bash
set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${THIS_DIR}/.."

cd "${REPO_ROOT}"

"${THIS_DIR}/test_up.sh"

set +e
docker compose --env-file .env.test -f docker-compose.test.yml run --rm tests \
  pytest --junitxml=junit-e2e.xml -m "e2e and not infra"
TEST_EXIT_CODE=$?
set -e

"${THIS_DIR}/test_down.sh"

exit "${TEST_EXIT_CODE}"
