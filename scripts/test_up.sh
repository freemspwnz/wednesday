#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# test_up.sh - Идемпотентный запуск тестовых контейнеров
# ============================================================================
#
# Container lifecycle: контейнеры запускаются один раз и переиспользуются
# всеми тестами (integration, e2e, e2e-infra). Останавливаются только
# через test-down.sh в конце CI pipeline.
#
# Требования:
# - Идемпотентность: если контейнеры уже запущены, пропускаем запуск
# - Healthchecks: ожидание готовности Postgres, Redis, Celery worker
# - Использование явного project name (wednesday_test) для изоляции
# - Использование .env.test для переменных окружения
#
# ============================================================================

COMPOSE_CMD="${COMPOSE_CMD:-}"
if [ -z "${COMPOSE_CMD}" ]; then
COMPOSE_PROJECT="wednesday_test"
  COMPOSE_FILE="tests/docker-compose.test.yml"
  COMPOSE_ENV="tests/.env.test"
  COMPOSE_CMD="docker compose -p ${COMPOSE_PROJECT} -f ${COMPOSE_FILE} --env-file ${COMPOSE_ENV}"
fi

echo "=== Проверка состояния тестовых контейнеров ==="

# Проверка идемпотентности: если контейнеры уже запущены, пропускаем
if ${COMPOSE_CMD} ps | grep -q "Up"; then
  echo "✓ Контейнеры уже запущены, пропускаем запуск (идемпотентность)"
  exit 0
fi

echo "=== Запуск тестовых контейнеров ==="

# ⚠️ КРИТИЧНО: на CI нужен timeout, чтобы не зависнуть навсегда.
# На macOS timeout/gtimeout может отсутствовать — в этом случае запускаем без таймаута.
TIMEOUT_CMD="$(command -v timeout 2>/dev/null || command -v gtimeout 2>/dev/null || echo "")"

if [[ -n "${TIMEOUT_CMD}" ]]; then
  echo "Используется timeout: ${TIMEOUT_CMD}"
  if ! "${TIMEOUT_CMD}" 300 ${COMPOSE_CMD} up -d --build; then
    echo "✗ Таймаут или ошибка при запуске контейнеров"
    ${COMPOSE_CMD} down -v || true
    exit 1
  fi
else
  echo "Timeout недоступен, запуск без таймаута (для macOS это нормально)"
  if ! ${COMPOSE_CMD} up -d --build; then
    echo "✗ Ошибка при запуске контейнеров"
    ${COMPOSE_CMD} down -v || true
    exit 1
  fi
fi

echo "=== Ожидание готовности сервисов (healthchecks) ==="

# Функция для получения health status контейнера
get_container_health() {
  local service_name=$1
  local health=""

  # Сначала пробуем получить ID контейнера через docker compose ps
  local container_id=$(${COMPOSE_CMD} ps -q ${service_name} 2>/dev/null | head -n1)
  if [ -n "$container_id" ]; then
    # Используем ID контейнера для проверки health status
    health=$(docker inspect --format='{{.State.Health.Status}}' "$container_id" 2>/dev/null || echo "")
  fi

  # Если не получили через ID, пробуем разные варианты имён контейнеров
  if [ -z "$health" ] || [ "$health" = "<no value>" ]; then
    health=$(docker inspect --format='{{.State.Health.Status}}' ${COMPOSE_PROJECT}-${service_name}-1 2>/dev/null || \
      docker inspect --format='{{.State.Health.Status}}' ${COMPOSE_PROJECT}_${service_name}_1 2>/dev/null || \
      docker inspect --format='{{.State.Health.Status}}' wednesday_${service_name} 2>/dev/null || \
      echo "")
  fi

  # Обрезаем пробелы и переводы строк, проверяем на пустоту
  health=$(echo "$health" | tr -d '[:space:]')
  if [ -z "$health" ] || [ "$health" = "<novalue>" ]; then
    echo ""
  else
    echo "$health"
  fi
}

# Ожидание готовности Postgres
echo "Ожидание готовности Postgres..."
timeout=60
while [ $timeout -gt 0 ]; do
  postgres_health=$(get_container_health "postgres_test")
  if [ "$postgres_health" = "healthy" ]; then
    echo "✓ Postgres готов"
    break
  fi
  if [ -n "$postgres_health" ]; then
    echo "  Postgres: $postgres_health (осталось попыток: $timeout)"
  else
    echo "  Postgres: starting (осталось попыток: $timeout)"
  fi
  sleep 2
  timeout=$((timeout - 1))
done

if [ $timeout -eq 0 ]; then
  echo "✗ Таймаут ожидания готовности Postgres"
  ${COMPOSE_CMD} down -v || true
  exit 1
fi

# Ожидание готовности Redis
echo "Ожидание готовности Redis..."
timeout=60
while [ $timeout -gt 0 ]; do
  redis_health=$(get_container_health "redis_test")
  if [ "$redis_health" = "healthy" ]; then
    echo "✓ Redis готов"
    break
  fi
  if [ -n "$redis_health" ]; then
    echo "  Redis: $redis_health (осталось попыток: $timeout)"
  else
    echo "  Redis: starting (осталось попыток: $timeout)"
  fi
  sleep 2
  timeout=$((timeout - 1))
done

if [ $timeout -eq 0 ]; then
  echo "✗ Таймаут ожидания готовности Redis"
  ${COMPOSE_CMD} down -v || true
  exit 1
fi

# Ожидание готовности Celery worker (опционально, но рекомендуется)
echo "Ожидание готовности Celery worker..."
timeout=120
while [ $timeout -gt 0 ]; do
  celery_health=$(get_container_health "celery-worker-test")
  if [ "$celery_health" = "healthy" ]; then
    echo "✓ Celery worker готов"
    break
  fi
  if [ -n "$celery_health" ]; then
    echo "  Celery worker: $celery_health (осталось попыток: $timeout)"
  else
    echo "  Celery worker: starting (осталось попыток: $timeout)"
  fi
  sleep 2
  timeout=$((timeout - 1))
done

if [ $timeout -eq 0 ]; then
  echo "⚠ Предупреждение: Celery worker не готов, но продолжаем (может быть не критично)"
fi

echo "✓ Все тестовые контейнеры запущены и готовы"
