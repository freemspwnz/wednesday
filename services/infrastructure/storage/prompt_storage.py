"""Сервис для работы с файловым хранилищем промптов."""

from __future__ import annotations

import asyncio
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from services.base.base_service import BaseService
from services.base.exceptions import StorageError
from utils.paths import PROMPTS_DIR

NEWLINE_CHARS = {"\n", "\r"}
CONTROL_MIN_CODE = 32
DELETE_CODE = 127


class PromptStorageService(BaseService):
    """Сервис для сохранения и загрузки промптов из файлового хранилища."""

    def __init__(self, base_dir: Path | None = None) -> None:
        """Инициализирует сервис хранилища промптов.

        Args:
            base_dir: Базовая директория для хранения промптов. Если None,
                используется PROMPTS_DIR по умолчанию.
        """
        super().__init__()
        self.base_dir: Path = base_dir or PROMPTS_DIR

    def _normalize_and_sanitize(self, prompt: str) -> str:
        """Нормализует и очищает промпт от управляющих символов.

        Args:
            prompt: Исходный промпт.

        Returns:
            Нормализованный и очищенный промпт.

        Raises:
            ValueError: Если промпт пуст после нормализации или очистки.
        """
        # Нормализуем промпт: убираем пробелы и переводы строк по краям
        normalized = prompt.strip()
        if not normalized:
            self.logger.warning(
                "Попытка сохранить пустой промпт после нормализации, запись пропущена",
            )
            raise ValueError("Prompt is empty after normalization")

        # Фильтрация управляющих символов
        cleaned_chars: list[str] = []
        for ch in normalized:
            code = ord(ch)
            if ch in NEWLINE_CHARS:
                cleaned_chars.append(ch)
            elif code < CONTROL_MIN_CODE or code == DELETE_CODE:
                continue
            else:
                cleaned_chars.append(ch)

        sanitized = "".join(cleaned_chars)
        if not sanitized.strip():
            self.logger.warning(
                "Промпт стал пустым после очистки управляющих символов, запись пропущена",
            )
            raise ValueError("Prompt is empty after control character sanitization")

        return sanitized

    async def save(
        self,
        prompt: str,
        folder: Path | str | None = None,
        source: str = "gigachat",
    ) -> str:
        """Сохраняет промпт в файловое хранилище.

        Сохраняет промпт в файл с временной меткой в имени. Выполняет нормализацию
        и очистку промпта от управляющих символов.

        Args:
            prompt: Текст промпта для сохранения.
            folder: Папка для сохранения. Если None, используется base_dir.
            source: Логическое имя источника/варианта для A/B-тестов (по умолчанию "gigachat").

        Returns:
            Путь к сохранённому файлу.

        Raises:
            ValueError: Если промпт пуст после нормализации или очистки управляющих символов.
            StorageError: При ошибках файловой системы (недостаточно прав, места на диске и т.д.).
        """
        try:
            # Нормализуем и очищаем промпт
            sanitized = self._normalize_and_sanitize(prompt)

            # Определяем путь для сохранения
            if folder is None:
                path = self.base_dir
            elif isinstance(folder, str):
                path = Path(folder)
            else:
                path = folder

            # Создаем директорию асинхронно
            await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)

            # Формируем имя файла
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{source}_prompt_{ts}.txt"
            file_path = path / filename

            # Для удобства диагностики в логах используем короткий hash
            prompt_hash = sha256(sanitized.encode("utf-8")).hexdigest()[:8]

            self.logger.info(f"Writing prompt {prompt_hash} to {file_path}")

            # Сохраняем файл асинхронно
            def _write_file() -> None:
                with file_path.open("w", encoding="utf-8") as f:
                    f.write(sanitized)

            await asyncio.to_thread(_write_file)

            self.logger.info(f"Промпт сохранён в файл: {file_path}")
            return str(file_path)
        except ValueError:
            raise
        except OSError as e:
            self.logger.error(
                f"Ошибка при сохранении промпта в файловое хранилище {self.base_dir}: {e}",
                exc_info=True,
            )
            raise StorageError(f"Ошибка при сохранении промпта: {e}") from e
        except Exception as e:
            raise StorageError(f"Неожиданная ошибка при сохранении промпта: {e}") from e

    async def load_all(self, folder: Path | str | None = None) -> list[str]:
        """Загружает все промпты из указанной папки.

        Читает все TXT файлы из указанной папки и возвращает их содержимое.

        Args:
            folder: Папка с промптами. Если None, используется base_dir.

        Returns:
            Список промптов из файлов. Пустые файлы пропускаются.

        Raises:
            StorageError: При критических ошибках доступа к файловой системе.
        """
        try:
            # Определяем путь
            if folder is None:
                path = self.base_dir
            elif isinstance(folder, str):
                path = Path(folder)
            else:
                path = folder

            # Проверяем существование папки асинхронно
            exists = await asyncio.to_thread(path.exists)
            if not exists:
                self.logger.warning(f"Папка с промптами не существует: {path}")
                return []

            # Получаем все TXT файлы асинхронно
            prompt_files = await asyncio.to_thread(lambda: list(path.glob("*.txt")))
            if not prompt_files:
                self.logger.debug(f"В папке {path} нет сохранённых промптов")
                return []

            # Загружаем содержимое всех файлов асинхронно
            prompts: list[str] = []
            for prompt_file in prompt_files:
                try:
                    content = await asyncio.to_thread(
                        prompt_file.read_text,
                        encoding="utf-8",
                    )
                    content_stripped = content.strip()
                    if content_stripped:
                        prompts.append(content_stripped)
                    else:
                        self.logger.warning(f"Файл промпта {prompt_file} пуст, пропускаем")
                except Exception as e:
                    self.logger.warning(f"Ошибка при чтении файла {prompt_file}: {e}")

            return prompts
        except OSError as e:
            self.logger.error(f"Ошибка при загрузке промптов из {folder}: {e}", exc_info=True)
            raise StorageError(f"Ошибка доступа к файловой системе: {e}") from e
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при загрузке промптов: {e}")
            return []
