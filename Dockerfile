# syntax=docker/dockerfile:1

FROM python:3.11-slim

# ⚠️ ВАЖНО: Устанавливаем timezone для корректной работы Celery Beat
ENV TZ=Europe/Amsterdam

# Предотвращаем создание .pyc файлов
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Создаём пользователя ---
RUN adduser --disabled-password --gecos "" app

# --- Рабочая директория ---
WORKDIR /app

# --- Копируем entrypoint скрипт раньше для лучшего кэширования ---
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# --- Устанавливаем gosu для переключения пользователя в entrypoint ---
RUN apt-get update && apt-get install -y --no-install-recommends gosu && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Копируем только зависимости сначала (кэш) ---
COPY requirements.txt .

# --- Устанавливаем зависимости ---
RUN pip install --no-cache-dir -r requirements.txt

# --- Копируем весь проект ---
COPY . .

# --- Копируем .env если нужно ---
# COPY .env .   # раскомментируй, если хочешь, чтобы файл был внутри контейнера

# --- Устанавливаем права на скрипты (они уже скопированы через COPY . .) ---
RUN chmod +x /app/scripts/*.py 2>/dev/null || true

# --- Создаём только необходимые директории для volumes (без /app/logs) ---
# При read_only: true каталоги должны существовать в образе для монтирования volumes
# /app/logs не нужен, т.к. логи пишутся только в stdout (Promtail читает Docker logs)
RUN mkdir -p /app/data/prompts /app/data/beat /app/data/frogs

# --- Меняем владельца ---
RUN chown -R app:app /app

# --- Устанавливаем entrypoint (будет выполняться от root, затем переключится на app) ---
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# --- Запуск от пользователя root (entrypoint переключит на app) ---
USER root

# --- Команда по умолчанию ---
CMD ["python3", "main.py"]
