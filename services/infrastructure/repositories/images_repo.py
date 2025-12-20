"""
Репозиторий изображений на базе PostgreSQL с content-addressable storage.

Таблица `images` хранит только метаданные:
- image_hash  — sha256‑хеш содержимого файла (hex, 64 символа), уникальный;
- prompt_hash — sha256‑хеш нормализованного промпта (FK на prompts.prompt_hash);
- path        — относительный путь к файлу, вида `data/frogs/<image_hash>.png`;
- created_at  — временная метка создания записи.

Основные сценарии:
- get_by_prompt_hash(prompt_hash)  — находит уже сгенерированное изображение для промпта (кеш‑хит);
- get_or_create_image(prompt_hash, image_bytes) — атомарно сохраняет файл и метаданные
  с учётом гонок (duplicate key → возврат существующей записи).

Файлы сохраняются в виде content-addressable storage:
имя файла = sha256(image_bytes).hexdigest() + ".png".
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Final

import asyncpg
from asyncpg import UniqueViolationError

from utils.logger import get_logger, log_all_methods
from utils.paths import FROGS_DIR

logger = get_logger(__name__)

_PNG_SUFFIX: Final[str] = ".png"


@dataclass(slots=True)
class ImageRecord:
    """Структура данных одной записи из таблицы images.

    Attributes:
        id: Уникальный идентификатор записи в базе данных.
        image_hash: SHA256-хеш содержимого файла изображения (hex, 64 символа).
        prompt_hash: SHA256-хеш нормализованного промпта (FK на prompts.prompt_hash).
        path: Относительный путь к файлу (data/frogs/<image_hash>.png).
        created_at: Временная метка создания записи.
    """

    id: int
    image_hash: str
    prompt_hash: str
    path: str
    created_at: datetime


@log_all_methods()
class ImagesRepo:
    """
    Репозиторий для работы с таблицей `images`.

    Ответственность:
    - поиск изображений по prompt_hash (кеш по промпту);
    - атомарная запись файла и метаданных по content-addressable схеме;
    - обработка гонок при параллельной генерации одного и того же промпта.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        """Инициализирует репозиторий изображений.

        Args:
            pool: Пул подключений PostgreSQL.
        """
        self._pool = pool
        self._logger = get_logger(__name__)

    @staticmethod
    def _row_to_record(row: object) -> ImageRecord:
        """Преобразует asyncpg.Record в ImageRecord.

        Args:
            row: Запись из базы данных (asyncpg.Record).

        Returns:
            Объект ImageRecord с данными из записи.
        """

        return ImageRecord(
            id=int(row["id"]),  # type: ignore[index]
            image_hash=str(row["image_hash"]),  # type: ignore[index]
            prompt_hash=str(row["prompt_hash"]),  # type: ignore[index]
            path=str(row["path"]),  # type: ignore[index]
            created_at=row["created_at"],  # type: ignore[index]
        )

    @staticmethod
    def _compute_hash(image_bytes: bytes) -> str:
        """Вычисляет SHA256-хеш содержимого изображения.

        Args:
            image_bytes: Байты изображения для хеширования.

        Returns:
            SHA256-хеш в hex-представлении (64 символа).
        """

        return sha256(image_bytes).hexdigest()

    @staticmethod
    def _filesystem_path_for_hash(image_hash: str) -> Path:
        """Возвращает путь на файловой системе для данного image_hash.

        Args:
            image_hash: SHA256-хеш изображения в hex-представлении.

        Returns:
            Путь к файлу изображения. Локально это `<project_root>/data/frogs/<image_hash>.png`,
            внутри контейнера — тот же путь, так как WORKDIR=/app.
        """

        base_dir = FROGS_DIR
        return base_dir / f"{image_hash}{_PNG_SUFFIX}"

    @staticmethod
    def _relative_path_for_hash(image_hash: str) -> str:
        """Возвращает путь для сохранения в БД (относительный путь как строка).

        Args:
            image_hash: SHA256-хеш изображения в hex-представлении.

        Returns:
            Относительный путь в формате `data/frogs/<image_hash>.png`.
        """

        return str(FROGS_DIR / f"{image_hash}{_PNG_SUFFIX}")

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        """Создаёт директорию, если её ещё нет.

        Args:
            path: Путь к директории для создания (создаются все родительские директории).
        """

        path.parent.mkdir(parents=True, exist_ok=True)

    async def get_by_prompt_hash(self, prompt_hash: str) -> ImageRecord | None:
        """Возвращает изображение по prompt_hash.

        Ищет изображение, связанное с указанным промптом через prompt_hash.
        Используется для проверки наличия кешированного изображения.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            ImageRecord если изображение найдено, None иначе.
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, image_hash, prompt_hash, path, created_at
                FROM images
                WHERE prompt_hash = $1;
                """,
                prompt_hash,
            )

        if row is None:
            self._logger.debug(f"Изображение для prompt_hash={prompt_hash} не найдено в таблице images")
            return None

        record = self._row_to_record(row)
        self._logger.info(
            "Изображение загружено из кеша: "
            f"prompt_hash={record.prompt_hash} image_hash={record.image_hash} path={record.path}",
        )
        return record

    async def load_image_bytes(self, record: ImageRecord) -> bytes:
        """Загружает байты изображения по записи из БД (асинхронно).

        Для надёжности путь на файловой системе вычисляется по image_hash,
        а не по полю path (path используется как канонический относительный путь для БД).

        Args:
            record: Запись ImageRecord с метаданными изображения.

        Returns:
            Байты изображения из файла.

        Raises:
            FileNotFoundError: Если файл изображения не найден на диске.
            OSError: При ошибке чтения файла.
        """
        fs_path = self._filesystem_path_for_hash(record.image_hash)
        # Используем asyncio.to_thread для чтения файла
        return await asyncio.to_thread(fs_path.read_bytes)

    async def get_or_create_image(self, prompt_hash: str, image_bytes: bytes) -> ImageRecord:
        """Гарантированно возвращает запись об изображении для данного prompt_hash.

        Алгоритм:
        1. Вычисляет image_hash = sha256(image_bytes).
        2. Сохраняет файл по временному пути и делает атомарный os.replace в
           `<data/frogs>/<image_hash>.png`, избегая перезаписи уже существующего файла.
        3. Вставляет запись в таблицу `images`. При duplicate key (prompt_hash или image_hash)
           читает существующую запись и возвращает её.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.
            image_bytes: Байты изображения для сохранения.

        Returns:
            ImageRecord с метаданными изображения (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных или файловой системе.
        """

        image_hash = self._compute_hash(image_bytes)
        fs_final_path = self._filesystem_path_for_hash(image_hash)
        db_path = self._relative_path_for_hash(image_hash)

        # 1. Атомарно сохраняем файл на диск (content-addressable storage).
        self._ensure_dir(fs_final_path)

        if fs_final_path.exists():
            # Файл уже есть — не перезаписываем, просто используем его.
            self._logger.info(
                f"Файл изображения уже существует для hash={image_hash} (path={fs_final_path}), переиспользуем",
            )
        else:
            # Создаём временный файл в /tmp для работы с read_only: true
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp", dir="/tmp") as tmp_file:
                fs_tmp_path = Path(tmp_file.name)
                try:
                    fs_tmp_path.write_bytes(image_bytes)
                    # os.replace обеспечивает атомарный move поверх существующего файла,
                    # но мы предварительно проверяем существование, поэтому перезапись
                    # возможна только при гонке между процессами.
                    fs_tmp_path.replace(fs_final_path)
                    self._logger.info(
                        f"Файл изображения сохранён: hash={image_hash} path={fs_final_path}",
                    )
                finally:
                    # На всякий случай удаляем временный файл, если он остался.
                    if fs_tmp_path.exists():
                        try:
                            fs_tmp_path.unlink()
                        except Exception:
                            # Логируем на уровне debug, чтобы не шуметь в проде.
                            self._logger.debug(f"Не удалось удалить временный файл изображения: {fs_tmp_path}")

        # 2. Вставляем или находим запись в БД.
        #
        # Важно: не оборачиваем операции в явный transaction‑контекст asyncpg.
        # При ошибке UniqueViolationError сама команда INSERT откатывается,
        # но соединение остаётся пригодным для последующих запросов SELECT.
        # Это позволяет реализовать паттерн "insert-or-select" без состояния
        # "current transaction is aborted" для всей сессии.
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO images (image_hash, prompt_hash, path)
                    VALUES ($1, $2, $3)
                    RETURNING id, image_hash, prompt_hash, path, created_at;
                    """,
                    image_hash,
                    prompt_hash,
                    db_path,
                )
                if row is not None:
                    record = self._row_to_record(row)
                    self._logger.info(
                        "Добавлена запись об изображении: "
                        f"prompt_hash={record.prompt_hash} image_hash={record.image_hash}",
                    )
                    return record
            except UniqueViolationError:
                # Гонка: другая транзакция успела вставить запись.
                # Просто логируем и переходим к чтению уже существующей записи.
                self._logger.info(
                    (
                        "Обнаружена гонка при вставке в таблицу images: "
                        f"дубликат ключа для image_hash={image_hash} или prompt_hash={prompt_hash}, "
                        "загружаю уже существующую запись"
                    ),
                )

            # Находим уже существующую запись (по prompt_hash — приоритетно, затем по image_hash).
            row = await conn.fetchrow(
                """
                SELECT id, image_hash, prompt_hash, path, created_at
                FROM images
                WHERE prompt_hash = $1 OR image_hash = $2
                ORDER BY created_at ASC
                LIMIT 1;
                """,
                prompt_hash,
                image_hash,
            )

        if row is None:  # pragma: no cover - крайне маловероятный деградационный сценарий
            raise RuntimeError("Failed to upsert image metadata: concurrent insert lost")

        record = self._row_to_record(row)
        return record
