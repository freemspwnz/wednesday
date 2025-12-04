#!/usr/bin/env bash
set -euo pipefail

echo "Запуск тестовых контейнеров..."

# ⚠️ КРИТИЧНО: на CI нужен timeout, чтобы не зависнуть навсегда.
# На macOS timeout/gtimeout может отсутствовать — в этом случае запускаем без таймаута.
TIMEOUT_CMD="$(command -v timeout 2>/dev/null || command -v gtimeout 2>/dev/null || echo "")"

if [[ -n "${TIMEOUT_CMD}" ]]; then
  echo "Используется timeout: ${TIMEOUT_CMD}"
  if ! "${TIMEOUT_CMD}" 300 docker compose --env-file .env.test -f docker-compose.test.yml up -d --build; then
    echo "✗ Таймаут или ошибка при запуске контейнеров"
    docker compose -f docker-compose.test.yml down -v || true
    exit 1
  fi
else
  echo "Timeout недоступен, запуск без таймаута (для macOS это нормально)"
  if ! docker compose --env-file .env.test -f docker-compose.test.yml up -d --build; then
    echo "✗ Ошибка при запуске контейнеров"
    docker compose -f docker-compose.test.yml down -v || true
    exit 1
  fi
fi

echo "✓ Контейнеры запущены (pytest сам подождёт готовности worker)"
