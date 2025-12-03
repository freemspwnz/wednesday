from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from services.prompt_generator import PromptStorage


def test_prompt_storage_writes_normalized_prompt_without_extra_quotes(tmp_path: Path, monkeypatch: Any) -> None:
    """
    Проверяем, что в файл записывается реальное содержимое промпта без лишних кавычек
    и ведущих/замыкающих пробелов.
    """

    # Подменяем логгер, чтобы не писать в реальные логи во время теста.
    fake_logger = MagicMock()
    monkeypatch.setattr("services.prompt_generator.get_logger", lambda *_args, **_kwargs: fake_logger)

    storage = PromptStorage(base_dir=tmp_path)

    # Промпт с кавычками и пробелами по краям.
    path_str = storage.save_prompt('   "A frog"   ', source="test")
    assert path_str is not None

    file_path = Path(path_str)
    assert file_path.is_file()
    content = file_path.read_text(encoding="utf-8")

    # Кавычки, пришедшие в теле промпта, сохраняются как есть,
    # но не добавляются новые и не дублируются.
    assert content == '"A frog"'


def test_prompt_storage_preserves_multiline_prompt_without_outer_spaces(tmp_path: Path, monkeypatch: Any) -> None:
    """
    Многострочные промпты сохраняются как есть, но без ведущих/замыкающих пробелов.
    Внутренняя структура (переводы строк и пробелы внутри строк) должна сохраниться.
    """

    fake_logger = MagicMock()
    monkeypatch.setattr("services.prompt_generator.get_logger", lambda *_args, **_kwargs: fake_logger)

    storage = PromptStorage(base_dir=tmp_path)

    multiline_prompt = "   line 1 \nsecond line\n\n  third line  "
    path_str = storage.save_prompt(multiline_prompt, source="multiline")
    assert path_str is not None

    file_path = Path(path_str)
    assert file_path.is_file()
    content = file_path.read_text(encoding="utf-8")

    # Ведущие/замыкающие пробелы по всему промпту удалены,
    # переводы строк внутри и пробелы в середине строк остаются.
    assert content == "line 1 \nsecond line\n\n  third line"


def test_prompt_storage_empty_prompt_raises_and_logs_warning(tmp_path: Path, monkeypatch: Any) -> None:
    """
    Пустой промпт после нормализации должен:
    - приводить к ValueError;
    - логироваться как предупреждение (гибкая ошибка, без падения сервиса выше по стеку).
    """

    fake_logger = MagicMock()
    monkeypatch.setattr("services.prompt_generator.get_logger", lambda *_args, **_kwargs: fake_logger)

    storage = PromptStorage(base_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.save_prompt("   ", source="empty")

    fake_logger.warning.assert_called_once()


def test_prompt_storage_works_with_tmpfs_like_volume(tmp_path: Path, monkeypatch: Any) -> None:
    """
    Эмулируем запись в директорию, которая ведёт себя как tmpfs‑volume (быстрое, эфемерное хранилище).
    Это позволяет в CI отловить регрессии, связанные с правами/созданием директории и записью.
    """

    fake_logger = MagicMock()
    monkeypatch.setattr("services.prompt_generator.get_logger", lambda *_args, **_kwargs: fake_logger)

    # Эмулируем отдельный "volume" внутри временной директории pytest.
    volume_dir = tmp_path / "prompt_volume"
    storage = PromptStorage(base_dir=volume_dir)

    path_str = storage.save_prompt("A frog from tmpfs", source="tmpfs")
    assert path_str is not None

    file_path = Path(path_str)
    assert file_path.is_file()
    assert file_path.read_text(encoding="utf-8") == "A frog from tmpfs"
