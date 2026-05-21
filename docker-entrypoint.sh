#!/bin/bash
set -e

prepare_directories() {
    mkdir -p /var/tmp/logs

    if [ "$(id -u)" = "0" ]; then
        chown -R app:app /var/tmp/logs 2>/dev/null || true
        chmod -R u+rwX,g+rwX,o+rX /var/tmp/logs 2>/dev/null || true
    fi
}

run_migrations_if_needed() {
    if [ ! -f /app/alembic.ini ]; then
        return 0
    fi
    if [ "$1" = "python3" ] && [ "${2:-}" = "main.py" ]; then
        echo "Running database migrations..."
        (cd /app && alembic upgrade head)
    fi
}

prepare_directories
run_migrations_if_needed "$@"

if [ "$(id -u)" = "0" ]; then
    exec gosu app "$@"
else
    exec "$@"
fi
