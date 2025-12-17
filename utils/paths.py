"""
Утилитный модуль с централизованными путями для файловых операций.

Все пути определены относительно корня проекта (WORKDIR=/app в контейнере).
При использовании относительных путей через pathlib.Path они автоматически
разрешаются относительно текущей рабочей директории.
"""

from __future__ import annotations

from pathlib import Path

# Базовая директория для данных
DATA_DIR = Path("data")

# Изображения жабы
FROGS_DIR = DATA_DIR / "frogs"

# Логи приложения
LOGS_DIR = Path("logs")

# Хранилище промптов GigaChat
PROMPTS_DIR = DATA_DIR / "prompts"

# Временные алиасы для обратной совместимости (будут удалены в следующих этапах)
# Deprecated: используйте FROGS_DIR вместо FROG_IMAGES_DIR
FROG_IMAGES_DIR: str = str(FROGS_DIR)
FROG_IMAGES_CONTAINER_PATH: str = f"/app/{FROG_IMAGES_DIR}"
LOGS_CONTAINER_PATH: str = "/app/logs"
PROMPTS_CONTAINER_PATH: str = "/app/data/prompts"


def resolve_frog_images_dir() -> Path:
    """Deprecated: используйте FROGS_DIR напрямую."""
    return FROGS_DIR


def resolve_logs_dir() -> Path:
    """Deprecated: используйте LOGS_DIR напрямую."""
    return LOGS_DIR


def resolve_prompts_dir() -> Path:
    """Deprecated: используйте PROMPTS_DIR напрямую."""
    return PROMPTS_DIR
