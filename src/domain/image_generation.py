"""Доменный сервис для генерации изображений.

Содержит чистую логику генерации изображений без зависимостей от инфраструктуры
(кэш, метрики, circuit breaker, файловое хранилище).

Включает валидацию и нормализацию промптов на уровне domain для инкапсуляции
бизнес-правил генерации изображений.
"""

from __future__ import annotations

from shared.base.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    ImageGenerationError,
    NetworkError,
)
from shared.protocols import ITextToImageClient

MIN_PROMPT_LENGTH = 1
"""Минимальная длина промпта для генерации изображения."""

MAX_PROMPT_LENGTH = 1000
"""Максимальная длина промпта для генерации изображения."""


class ImageGenerationService:
    """Доменный сервис для генерации изображений.

    Выполняет валидацию и нормализацию промптов, затем чистую генерацию
    изображений через ITextToImageClient без зависимостей от инфраструктуры
    (кэш, метрики, circuit breaker).

    Инкапсулирует бизнес-правила генерации:
    - Валидация длины промпта (MIN_PROMPT_LENGTH - MAX_PROMPT_LENGTH)
    - Нормализация промпта (удаление пробелов по краям и лишних пробелов внутри)
    """

    def __init__(self, image_client: ITextToImageClient) -> None:
        """Инициализирует сервис генерации изображений.

        Args:
            image_client: Клиент для генерации изображений по текстовому промпту.
        """
        self._image_client = image_client

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        """Нормализует промпт для генерации изображения.

        Выполняет базовую нормализацию:
        - Удаляет пробелы по краям
        - Удаляет лишние пробелы внутри текста

        Args:
            prompt: Исходный промпт

        Returns:
            Нормализованный промпт
        """
        normalized = prompt.strip()
        normalized = " ".join(normalized.split())  # Удаление лишних пробелов
        return normalized

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        """Валидирует промпт перед генерацией.

        Args:
            prompt: Нормализованный промпт для проверки

        Raises:
            ValueError: Если промпт не соответствует требованиям
        """
        if not prompt:
            raise ValueError("Промпт не может быть пустым")

        if len(prompt) < MIN_PROMPT_LENGTH:
            raise ValueError(f"Промпт слишком короткий (минимум {MIN_PROMPT_LENGTH} символов)")

        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Промпт слишком длинный (максимум {MAX_PROMPT_LENGTH} символов, получено {len(prompt)})")

    async def generate(
        self,
        prompt: str,
        user_id: int | None = None,
    ) -> bytes:
        """Генерирует изображение по промпту.

        Выполняет валидацию и нормализацию промпта, затем чистую генерацию
        через ITextToImageClient без кэширования, метрик и других
        инфраструктурных зависимостей.

        Retry логика применяется на уровне клиента (ITextToImageClient).

        Args:
            prompt: Текстовый промпт для генерации изображения.
            user_id: Идентификатор пользователя для логирования (опционально).

        Returns:
            Байты изображения.

        Raises:
            ImageGenerationError: При невалидном промпте или критических ошибках генерации.
        """
        user_id_str = str(user_id) if user_id is not None else None

        # Нормализация промпта
        normalized_prompt = self._normalize_prompt(prompt)

        # Валидация промпта
        try:
            self._validate_prompt(normalized_prompt)
        except ValueError as e:
            raise ImageGenerationError(f"Невалидный промпт: {e}") from e

        try:
            image_data = await self._image_client.generate(normalized_prompt, user_id=user_id_str)
            return image_data

        except AuthenticationError as exc:
            raise ImageGenerationError("Ошибка аутентификации при генерации изображения") from exc
        except NetworkError as exc:
            raise ImageGenerationError("Сетевая ошибка при генерации изображения") from exc
        except APIError as exc:
            raise ImageGenerationError(f"Ошибка API при генерации изображения: {exc}") from exc
        except ClientError as exc:
            raise ImageGenerationError("Ошибка клиента при генерации изображения") from exc
        except Exception as e:
            raise ImageGenerationError(f"Ошибка при генерации изображения: {e}") from e
