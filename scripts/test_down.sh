#!/usr/bin/env bash
set -euo pipefail

echo "Остановка тестовых контейнеров..."
docker compose -f docker-compose.test.yml down -v || true
echo "✓ Контейнеры остановлены"
