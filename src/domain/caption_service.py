"""Сервис для работы с подписями к изображениям."""

from __future__ import annotations

import random

from shared.base.base_service import BaseService


class CaptionService(BaseService):
    """Сервис для выбора подписей к изображениям.

    Инкапсулирует бизнес-логику выбора подписей для сгенерированных изображений.
    """

    def __init__(self, captions: list[str] | tuple[str, ...]) -> None:
        """Инициализирует сервис подписей.

        Args:
            captions: Список доступных подписей.

        Raises:
            ValueError: Если список подписей пуст.
        """
        super().__init__()
        if not captions:
            raise ValueError("Список подписей не может быть пустым")
        self._captions = list(captions)

    def get_random_caption(self) -> str:
        """Возвращает случайную подпись для изображения.

        Returns:
            Случайная подпись из доступных.
        """
        return random.choice(self._captions)

    def get_all_captions(self) -> list[str]:
        """Возвращает все доступные подписи.

        Returns:
            Список всех подписей.
        """
        return self._captions.copy()

    def has_captions(self) -> bool:
        """Проверяет, есть ли доступные подписи.

        Returns:
            True если есть подписи, False иначе.
        """
        return bool(self._captions)
