# syntax=docker/dockerfile:1

FROM python:3.11-slim

# ⚠️ ВАЖНО: Устанавливаем timezone для корректной работы Celery Beat
ENV TZ=Europe/Amsterdam
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Создаём пользователя ---
RUN adduser --disabled-password --gecos "" app

# --- Рабочая директория ---
WORKDIR /app

# --- Копируем только зависимости сначала (кэш) ---
COPY requirements.txt .

# --- Устанавливаем зависимости ---
RUN pip install --no-cache-dir -r requirements.txt

# --- Копируем весь проект ---
COPY . .

# --- Копируем .env если нужно ---
# COPY .env .   # раскомментируй, если хочешь, чтобы файл был внутри контейнера

# --- Устанавливаем gosu для переключения пользователя в entrypoint ---
RUN apt-get update && apt-get install -y --no-install-recommends gosu && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Копируем entrypoint скрипт ---
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# --- Устанавливаем права на скрипты (они уже скопированы через COPY . .) ---
RUN chmod +x /app/scripts/*.py 2>/dev/null || true

# --- Создаём директории для логов и данных (если их нет) ---
RUN mkdir -p /app/logs /app/data/prompts /app/data/beat

# --- Меняем владельца ---
RUN chown -R app:app /app

# --- Устанавливаем entrypoint (будет выполняться от root, затем переключится на app) ---
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# --- Запуск от пользователя root (entrypoint переключит на app) ---
USER root

# --- Команда по умолчанию ---
CMD ["python3", "main.py"]
