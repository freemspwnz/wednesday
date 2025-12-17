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
