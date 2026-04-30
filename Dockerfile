# syntax=docker/dockerfile:1

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev libpq-dev && \
    rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=2.1.2 \
POETRY_VIRTUALENVS_CREATE=false \
POETRY_NO_INTERACTION=1 \
POETRY_CACHE_DIR=/tmp/poetry_cache

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock README.md ./

RUN poetry install --only main --no-root --no-ansi \
    && rm -rf "$POETRY_CACHE_DIR"

COPY wednesday ./wednesday

RUN poetry install --only main --no-ansi \
    && rm -rf "$POETRY_CACHE_DIR"

# --- Stage 2: Final ---
FROM python:3.12-slim

ENV TZ=Europe/Amsterdam \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata gosu && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# Создаем пользователя заранее
RUN useradd --create-home --shell /bin/bash app

# Зависимости и установленные пакеты из builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=app:app wednesday/ /app/wednesday/

# Копируем entrypoint и даем права
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /app/wednesday

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python3", "main.py"]
