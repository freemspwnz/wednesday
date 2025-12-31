from pathlib import Path

from shared.paths import DATA_DIR, FROGS_DIR, PROMPTS_DIR


def test_data_dir() -> None:
    """Проверяем, что базовая директория данных определена корректно."""
    assert DATA_DIR == Path("data")


def test_frogs_dir() -> None:
    """Проверяем, что директория изображений определена корректно."""
    assert FROGS_DIR == Path("data/frogs")


def test_prompts_dir() -> None:
    """Проверяем, что директория промптов определена корректно."""
    assert PROMPTS_DIR == Path("data/prompts")
