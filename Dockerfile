# syntax=docker/dockerfile:1

ARG UV_VERSION=0.12.1
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock README.md LICENSE ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY wednesday ./wednesday

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# --- Stage 2: Final ---
FROM python:3.12-slim

ENV TZ=Europe/Amsterdam \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata gosu && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app wednesday/ /app/wednesday/
COPY --chown=app:app alembic/ /app/alembic/
COPY --chown=app:app alembic.ini /app/alembic.ini

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /app/wednesday

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python3", "main.py"]
