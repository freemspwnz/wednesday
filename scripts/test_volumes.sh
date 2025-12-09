#!/bin/bash
# E2E тест для проверки volumes в Docker контейнерах
# Тесты volumes должны быть E2E (shell-based), так как volumes доступны только внутри Docker контейнеров

set -e

echo "🔍 Проверка volumes..."

# Проверить, что volumes смонтированы в bot
echo "Проверка volumes в bot..."
docker compose exec bot test -d /app/data/frogs || { echo "❌ /app/data/frogs не существует в bot"; exit 1; }
docker compose exec bot test -d /app/data/prompts || { echo "❌ /app/data/prompts не существует в bot"; exit 1; }

# Проверить, что запись в volumes работает
echo "Проверка записи в volumes..."
docker compose exec bot touch /app/data/frogs/test.txt || { echo "❌ Не удалось создать файл в /app/data/frogs"; exit 1; }
docker compose exec bot rm /app/data/frogs/test.txt || { echo "❌ Не удалось удалить файл из /app/data/frogs"; exit 1; }

docker compose exec bot touch /app/data/prompts/test.txt || { echo "❌ Не удалось создать файл в /app/data/prompts"; exit 1; }
docker compose exec bot rm /app/data/prompts/test.txt || { echo "❌ Не удалось удалить файл из /app/data/prompts"; exit 1; }

# Проверить изоляцию между контейнерами (volumes должны быть общими)
echo "Проверка изоляции между контейнерами..."
docker compose exec celery-worker test -d /app/data/frogs || { echo "❌ /app/data/frogs не существует в celery-worker"; exit 1; }
docker compose exec celery-worker test -d /app/data/prompts || { echo "❌ /app/data/prompts не существует в celery-worker"; exit 1; }

# Проверить, что /app/logs не существует (логи только в stdout)
echo "Проверка отсутствия /app/logs (логи только в stdout)..."
docker compose exec bot test ! -d /app/logs || { echo "⚠️  /app/logs существует, но не должен (логи только в stdout)"; }

# Проверить, что /tmp доступен для записи (tmpfs)
echo "Проверка доступности /tmp (tmpfs)..."
docker compose exec bot touch /tmp/test.txt || { echo "❌ Не удалось создать файл в /tmp"; exit 1; }
docker compose exec bot rm /tmp/test.txt || { echo "❌ Не удалось удалить файл из /tmp"; exit 1; }

echo "✅ Все volumes работают корректно"
