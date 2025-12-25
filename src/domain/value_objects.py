"""Value Objects доменного слоя.

Содержит неизменяемые объекты-значения, инкапсулирующие бизнес-правила валидации и нормализации.
"""

from __future__ import annotations

MIN_PROMPT_LENGTH = 1
"""Минимальная длина промпта для генерации изображения."""

MAX_PROMPT_LENGTH = 1000
"""Максимальная длина промпта для генерации изображения."""


class Prompt:
    """Value Object для промпта генерации изображения.

    Инкапсулирует бизнес-правила валидации и нормализации промпта.
    """

    def __init__(self, raw_text: str) -> None:
        """Создает валидированный и нормализованный промпт.

        Args:
            raw_text: Исходный текст промпта.

        Raises:
            ValueError: Если промпт не соответствует требованиям.
        """
        normalized = self._normalize(raw_text)
        self._validate(normalized)
        self._value = normalized

    @property
    def value(self) -> str:
        """Возвращает нормализованное значение промпта."""
        return self._value

    @staticmethod
    def _normalize(text: str) -> str:
        """Нормализует текст промпта.

        Выполняет базовую нормализацию:
        - Удаляет пробелы по краям
        - Удаляет лишние пробелы внутри текста

        Args:
            text: Исходный текст промпта.

        Returns:
            Нормализованный текст промпта.
        """
        normalized = text.strip()
        normalized = " ".join(normalized.split())
        return normalized

    @staticmethod
    def _validate(text: str) -> None:
        """Валидирует промпт.

        Args:
            text: Нормализованный текст промпта для проверки.

        Raises:
            ValueError: Если промпт не соответствует требованиям.
        """
        if not text:
            raise ValueError("Промпт не может быть пустым")

        if len(text) < MIN_PROMPT_LENGTH:
            raise ValueError(f"Промпт слишком короткий (минимум {MIN_PROMPT_LENGTH} символов)")

        if len(text) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Промпт слишком длинный (максимум {MAX_PROMPT_LENGTH} символов, получено {len(text)})")

    def __str__(self) -> str:
        """Возвращает строковое представление промпта."""
        return self._value

    def __repr__(self) -> str:
        """Возвращает представление объекта для отладки."""
        return f"Prompt(value={self._value!r})"

    def __eq__(self, other: object) -> bool:
        """Проверяет равенство двух промптов."""
        if not isinstance(other, Prompt):
            return False
        return self._value == other._value

    def __hash__(self) -> int:
        """Возвращает хеш промпта для использования в множествах и словарях."""
        return hash(self._value)


class UserID:
    """Value Object для идентификатора пользователя.

    Инкапсулирует конвертацию между доменным типом (int для Telegram ID)
    и форматом протоколов инфраструктуры (str для логирования).
    """

    def __init__(self, value: int | None) -> None:
        """Создает UserID из доменного типа.

        Args:
            value: Идентификатор пользователя как int (Telegram ID) или None.
        """
        self._value = value

    @property
    def value(self) -> int | None:
        """Возвращает доменное значение (int).

        Returns:
            Идентификатор пользователя как int или None.
        """
        return self._value

    def for_logging(self) -> str | None:
        """Возвращает значение для логирования (str).

        Используется при передаче в протоколы инфраструктуры,
        где требуется строковое представление user_id.

        Returns:
            Строковое представление user_id или None.
        """
        return str(self._value) if self._value is not None else None

    def __bool__(self) -> bool:
        """Проверяет, задан ли user_id.

        Returns:
            True если user_id не None, False иначе.
        """
        return self._value is not None

    def __eq__(self, other: object) -> bool:
        """Проверяет равенство двух UserID.

        Args:
            other: Объект для сравнения.

        Returns:
            True если значения равны, False иначе.
        """
        if not isinstance(other, UserID):
            return False
        return self._value == other._value

    def __hash__(self) -> int:
        """Возвращает хеш UserID для использования в множествах и словарях.

        Returns:
            Хеш значения user_id или 0 для None.
        """
        return hash(self._value) if self._value is not None else 0

    def __repr__(self) -> str:
        """Возвращает представление объекта для отладки.

        Returns:
            Строковое представление UserID.
        """
        return f"UserID(value={self._value})"
