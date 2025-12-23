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
