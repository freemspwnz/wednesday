"""
Файловое хранилище промптов.

Модуль отвечает за:
- сохранение промптов в `data/prompts/`;
- чтение случайных промптов из файлового хранилища для fallback;
- подготовку структуры для будущих A/B-тестов разных вариантов промптов.

Примечание: синхронный клиент GigaChat был удалён, так как он устарел.
Используется асинхронный GigaChatTextClient из services/clients/gigachat_text.py.
"""

import random
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from utils.logger import get_logger
from utils.paths import PROMPTS_CONTAINER_PATH, resolve_prompts_dir

NEWLINE_CHARS = {"\n", "\r"}
CONTROL_MIN_CODE = 32
DELETE_CODE = 127


class PromptStorage:
    """
    Простое файловое хранилище промптов.

    Вынесено в отдельный класс, чтобы:
    - централизовать работу с `data/prompts/`;
    - упростить повторное использование (генератор изображений, доп. сервисы);
    - подготовить почву для A/B-тестов (разные источники/варианты промптов по полю `source`).
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.logger = get_logger(__name__)
        # Используем централизованный резолвер путей, чтобы:
        # - при локальном запуске работать с <project_root>/data/prompts;
        # - внутри контейнера писать строго в /app/data/prompts, которое должно быть примонтировано
        #   как Docker volume (prompt_storage), а не запекаться в образ.
        self.base_dir: Path = base_dir or resolve_prompts_dir()
        # Создаём директорию один раз при инициализации, чтобы не требовать ручного создания.
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_prompt(self, prompt: str, source: str = "gigachat") -> str | None:
        """
        Сохраняет промпт в файл в папке `data/prompts/`.

        Args:
            prompt: текст промпта
            source: логическое имя источника/варианта (для A/B-тестов)

        Returns:
            Путь к сохранённому файлу или None при ошибке записи.

        Валидационные ошибки (например, пустой промпт после нормализации) выражаются
        через ValueError и могут обрабатываться вызывающим кодом как гибкие.
        """
        # Нормализуем промпт: убираем пробелы и переводы строк по краям,
        # но не трогаем внутренние пробелы и многострочную структуру.
        normalized = prompt.strip()
        if not normalized:
            # Пустой промпт после нормализации — логическая ошибка,
            # не хотим создавать "битые" файлы в файловом хранилище.
            self.logger.warning(
                "Попытка сохранить пустой промпт после нормализации, запись пропущена",
            )
            raise ValueError("Prompt is empty after normalization")

        # Фильтрация управляющих символов:
        # - разрешаем перевод строки (\n и \r) для многострочных промптов;
        # - отбрасываем прочие управляющие символы (<0x20 и 0x7F), которые не несут
        #   смысловой нагрузки и могут испортить отображение файла;
        # - не добавляем и не удаляем кавычки внутри текста, только то, что пришло
        #   от вызывающего кода / внешнего API.
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
            # После удаления управляющих символов промпт может оказаться пустым.
            self.logger.warning(
                "Промпт стал пустым после очистки управляющих символов, запись пропущена",
            )
            raise ValueError("Prompt is empty after control character sanitization")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{source}_prompt_{ts}.txt"
        file_path = self.base_dir / filename

        # Для удобства диагностики в логах используем короткий hash от финального текста.
        prompt_hash = sha256(sanitized.encode("utf-8")).hexdigest()[:8]

        # Пример логирования через loguru‑совместимый логгер:
        # пишем как будто внутри контейнера, чтобы путь совпадал
        # с ожидаемым mount‑путём volume `prompt_storage`.
        self.logger.info(
            f"Writing prompt {prompt_hash} to {PROMPTS_CONTAINER_PATH}/{filename}",
        )

        # Явная запись через open/write вместо write_text() — чтобы не полагаться
        # на поведение pathlib и очевидно указать кодировку.
        try:
            with file_path.open("w", encoding="utf-8") as f:
                f.write(sanitized)
        except OSError as e:
            # Ошибка записи не должна ломать генерацию промпта — только логируем.
            self.logger.error(
                f"Ошибка при сохранении промпта в файловое хранилище {self.base_dir}: {e}",
                exc_info=True,
            )
            return None

        self.logger.info(f"Промпт сохранён в файл: {file_path}")
        return str(file_path)

    def get_random_prompt(self) -> str | None:
        """
        Возвращает случайный промпт из сохранённых файлов.

        Используется другими сервисами как файловый fallback при сбоях GigaChat.
        """
        try:
            # Повторно гарантируем наличие папки на случай, если её удалили между запусками.
            self.base_dir.mkdir(parents=True, exist_ok=True)
            prompt_files = list(self.base_dir.glob("*.txt"))
            if not prompt_files:
                self.logger.debug(f"В папке {self.base_dir} нет сохранённых промптов для fallback")
                return None

            random_file = random.choice(prompt_files)
            content = random_file.read_text(encoding="utf-8").strip()
            if not content:
                self.logger.warning(f"Файл промпта {random_file} пуст, пропускаем")
                return None

            self.logger.info(f"Выбран fallback-промпт из файла: {random_file}")
            return content
        except Exception as e:
            self.logger.error(f"Ошибка при чтении fallback-промпта из файлов: {e}", exc_info=True)
            return None
