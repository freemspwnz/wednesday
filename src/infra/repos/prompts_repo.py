"""
Репозиторий промптов на базе PostgreSQL.

Таблица `prompts` хранит:
- исходный текст промпта (raw_text);
- нормализованный текст (normalized_text);
- детерминированный sha256‑хэш нормализованного текста (prompt_hash) для дедупликации;
- временную метку создания и необязательную A/B‑группу.

Базовые операции:
- get_or_create_prompt(prompt_text) — нормализует текст, считает hash и возвращает
  существующую запись или создаёт новую;
- get_prompt_by_hash(prompt_hash) — ищет промпт по hash;
- get_random_prompt() — возвращает случайный сохранённый промпт (используется как fallback).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

import asyncpg

from infra.logging.logger import get_logger, log_all_methods
from shared.models import PromptRecordDTO

logger = get_logger(__name__)


@dataclass(slots=True)
class PromptRecord:
    """Структура данных одной записи из таблицы prompts.

    Attributes:
        id: Уникальный идентификатор записи в базе данных.
        raw_text: Исходный текст промпта (как был введён).
        normalized_text: Нормализованный текст промпта (после обработки).
        prompt_hash: SHA256-хеш нормализованного текста (hex, 64 символа).
        created_at: Временная метка создания записи.
        ab_group: A/B группа для промпта (опционально).
    """

    id: int
    raw_text: str
    normalized_text: str
    prompt_hash: str
    created_at: datetime
    ab_group: str | None


@log_all_methods()
class PromptsRepo:
    """
    Репозиторий для работы с таблицей `prompts`.

    Все методы асинхронные и используют Postgres как единственный источник истины
    для метаданных промптов (файловое хранилище — только как дополнительный backup/fallback).
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        """Инициализирует репозиторий промптов.

        Args:
            pool: Пул подключений PostgreSQL.
        """
        self._pool = pool
        self.logger = get_logger(__name__)

    @staticmethod
    def _normalize(prompt_text: str) -> str:
        """Возвращает нормализованный текст промпта.

        Сейчас нормализация минимальна: strip() по краям.
        Важно хранить и raw, и normalized, чтобы можно было откатить нормализацию.

        Args:
            prompt_text: Исходный текст промпта для нормализации.

        Returns:
            Нормализованный текст промпта (с удалёнными пробелами по краям).
        """

        return prompt_text.strip()

    @staticmethod
    def _hash(normalized: str) -> str:
        """Вычисляет SHA256-хеш нормализованного текста.

        Args:
            normalized: Нормализованный текст промпта.

        Returns:
            SHA256-хеш в hex-представлении (64 символа).
        """

        return sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_record(row: object) -> PromptRecord:
        """Преобразует asyncpg.Record в PromptRecord.

        Args:
            row: Запись из базы данных (asyncpg.Record).

        Returns:
            Объект PromptRecord с данными из записи.
        """

        return PromptRecord(
            id=int(row["id"]),  # type: ignore[index]
            raw_text=str(row["raw_text"]),  # type: ignore[index]
            normalized_text=str(row["normalized_text"]),  # type: ignore[index]
            prompt_hash=str(row["prompt_hash"]),  # type: ignore[index]
            created_at=row["created_at"],  # type: ignore[index]
            ab_group=row["ab_group"],  # type: ignore[index]
        )

    @staticmethod
    def _to_dto(record: PromptRecord) -> PromptRecordDTO:
        """Конвертирует внутренний PromptRecord в PromptRecordDTO.

        Args:
            record: Внутренний объект PromptRecord.

        Returns:
            PromptRecordDTO для использования в протоколах.
        """
        return PromptRecordDTO(
            id=record.id,
            raw_text=record.raw_text,
            normalized_text=record.normalized_text,
            prompt_hash=record.prompt_hash,
            created_at=record.created_at,
            ab_group=record.ab_group,
        )

    async def get_or_create_prompt(self, prompt_text: str) -> PromptRecordDTO:
        """Возвращает существующий или создаёт новый промпт.

        Алгоритм:
        1. Нормализует текст: normalized = prompt_text.strip()
        2. Вычисляет хеш: prompt_hash = sha256(normalized.encode("utf-8")).hexdigest()
        3. Если запись с таким hash уже есть — возвращает её
        4. Иначе создаёт новую с ab_group=NULL

        Args:
            prompt_text: Исходный текст промпта.

        Returns:
            PromptRecordDTO с метаданными промпта (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """

        normalized = self._normalize(prompt_text)
        prompt_hash = self._hash(normalized)

        async with self._pool.acquire() as conn:
            # 1. Пытаемся найти уже существующую запись.
            row = await conn.fetchrow(
                """
                SELECT id, raw_text, normalized_text, prompt_hash, created_at, ab_group
                FROM prompts
                WHERE prompt_hash = $1;
                """,
                prompt_hash,
            )
            if row is not None:
                record = self._row_to_record(row)
                self.logger.info(f"Prompt exists: {prompt_hash} (id={record.id})")
                return self._to_dto(record)

            # 2. Создаём новую запись. ab_group пока всегда NULL,
            #    в будущем сюда может добавиться логика A/B‑распределения.
            row = await conn.fetchrow(
                """
                INSERT INTO prompts (raw_text, normalized_text, prompt_hash, ab_group)
                VALUES ($1, $2, $3, NULL)
                ON CONFLICT (prompt_hash) DO NOTHING
                RETURNING id, raw_text, normalized_text, prompt_hash, created_at, ab_group;
                """,
                prompt_text,
                normalized,
                prompt_hash,
            )

            if row is None:
                # Возможен condition‑race: кто‑то другой вставил такую же строку
                # между SELECT и INSERT. В этом случае просто перечитываем.
                row = await conn.fetchrow(
                    """
                    SELECT id, raw_text, normalized_text, prompt_hash, created_at, ab_group
                    FROM prompts
                    WHERE prompt_hash = $1;
                    """,
                    prompt_hash,
                )
                if row is None:  # pragma: no cover - крайне маловероятный кейс
                    raise RuntimeError("Failed to upsert prompt: concurrent insert lost")

            record = self._row_to_record(row)
            self.logger.info(f"Prompt created: {prompt_hash} (id={record.id})")
            return self._to_dto(record)

    async def get_prompt_by_hash(self, prompt_hash: str) -> PromptRecordDTO | None:
        """Возвращает промпт по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            PromptRecordDTO если промпт найден, None иначе.
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, raw_text, normalized_text, prompt_hash, created_at, ab_group
                FROM prompts
                WHERE prompt_hash = $1;
                """,
                prompt_hash,
            )
        if row is None:
            self.logger.debug(f"Prompt not found for hash: {prompt_hash}")
            return None

        record = self._row_to_record(row)
        self.logger.info(f"Prompt loaded by hash: {prompt_hash} (id={record.id})")
        return self._to_dto(record)

    async def get_random_prompt(self) -> PromptRecord | None:
        """Возвращает случайный промпт из таблицы.

        Используется как fallback при недоступности GigaChat.

        Returns:
            PromptRecord со случайным промптом или None, если таблица пуста.
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, raw_text, normalized_text, prompt_hash, created_at, ab_group
                FROM prompts
                ORDER BY random()
                LIMIT 1;
                """,
            )
        if row is None:
            self.logger.debug("get_random_prompt: таблица prompts пуста")
            return None

        record = self._row_to_record(row)
        self.logger.info(f"Random prompt selected: {record.prompt_hash} (id={record.id})")
        return record
