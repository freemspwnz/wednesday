#!/usr/bin/env bash
set -euo pipefail

DOCKER_COMPOSE="docker compose"
IMAGE_NAME="${IMAGE_NAME:-wednesday-bot}"
TIMEOUT_SEC="${TIMEOUT_SEC:-60}"

echo "Очистка старого образа ${IMAGE_NAME}:local..."
docker rmi "${IMAGE_NAME}:local" 2>/dev/null || true
echo "Сборка нового образа ${IMAGE_NAME}:local..."
docker build -t "${IMAGE_NAME}:local" .

echo "=== Запуск бота в Docker-контейнерах ==="
echo "Очистка старых контейнеров..."
${DOCKER_COMPOSE} down
echo "Поднятие боевых контейнеров Postgres и Redis..."
${DOCKER_COMPOSE} up -d postgres redis

echo "Ожидание готовности сервисов..."
timeout=${TIMEOUT_SEC}
while [ ${timeout} -gt 0 ]; do
  postgres_health=$(docker inspect --format='{{.State.Health.Status}}' wednesday_postgres 2>/dev/null || echo "starting")
  redis_health=$(docker inspect --format='{{.State.Health.Status}}' wednesday_redis 2>/dev/null || echo "starting")
  if [ "${postgres_health}" = "healthy" ] && [ "${redis_health}" = "healthy" ]; then
    echo "✓ Сервисы готовы"
    break
  fi
  echo "Ожидание сервисов... (Postgres: ${postgres_health}, Redis: ${redis_health})"
  sleep 2
  timeout=$((timeout-1))
done

if [ ${timeout} -eq 0 ]; then
  echo "✗ Таймаут ожидания готовности сервисов"
  exit 1
fi

echo "Запуск бота..."
${DOCKER_COMPOSE} up bot
