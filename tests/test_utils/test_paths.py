from pathlib import Path

from utils.paths import DATA_DIR, FROGS_DIR, LOGS_DIR, PROMPTS_DIR


def test_data_dir() -> None:
    """Проверяем, что базовая директория данных определена корректно."""
    assert DATA_DIR == Path("data")


def test_frogs_dir() -> None:
    """Проверяем, что директория изображений определена корректно."""
    assert FROGS_DIR == Path("data/frogs")


def test_logs_dir() -> None:
    """Проверяем, что директория логов определена корректно."""
    assert LOGS_DIR == Path("logs")


def test_prompts_dir() -> None:
    """Проверяем, что директория промптов определена корректно."""
    assert PROMPTS_DIR == Path("data/prompts")
