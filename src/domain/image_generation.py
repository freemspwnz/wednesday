"""Доменный сервис для генерации изображений.

Содержит чистую логику генерации изображений без зависимостей от инфраструктуры
(кэш, метрики, circuit breaker, файловое хранилище).

Включает валидацию и нормализацию промптов на уровне domain для инкапсуляции
бизнес-правил генерации изображений.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.base.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    ImageGenerationError,
    NetworkError,
)
from shared.protocols import ITextToImageClient
from shared.retry import retry_standard

MIN_PROMPT_LENGTH = 1
"""Минимальная длина промпта для генерации изображения."""

MAX_PROMPT_LENGTH = 1000
"""Максимальная длина промпта для генерации изображения."""


class ImageGenerationService(BaseService):
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
        super().__init__()
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

    @retry_standard(service_name="image_generation", method_name="generate")
    async def generate(
        self,
        prompt: str,
        user_id: int | None = None,
    ) -> bytes:
        """Генерирует изображение по промпту.

        Выполняет валидацию и нормализацию промпта, затем чистую генерацию
        через ITextToImageClient без кэширования, метрик и других
        инфраструктурных зависимостей.

        Retry логика применяется автоматически для сетевых ошибок через декоратор.

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
            self.logger.warning(f"Невалидный промпт: {e}")
            raise ImageGenerationError(f"Невалидный промпт: {e}") from e

        try:
            self.log_event(
                event="image_generation_started",
                user_id=user_id_str,
                status="started",
                level="info",
                message=f"Начинаю генерацию изображения для промпта: {normalized_prompt[:100]}...",
            )

            image_data = await self._image_client.generate(normalized_prompt, user_id=user_id_str)

            self.log_event(
                event="image_generation_success",
                user_id=user_id_str,
                status="success",
                level="info",
                message="Изображение успешно сгенерировано",
            )
            return image_data

        except AuthenticationError as exc:
            # Специфичная обработка ошибок аутентификации
            self.log_event(
                event="image_generation_failed",
                user_id=user_id_str,
                status="auth_error",
                level="error",
                message=f"Ошибка аутентификации при генерации изображения: {exc}",
            )
            raise ImageGenerationError("Ошибка аутентификации при генерации изображения") from exc
        except NetworkError as exc:
            # Специфичная обработка сетевых ошибок (можно retry)
            self.log_event(
                event="image_generation_failed",
                user_id=user_id_str,
                status="network_error",
                level="warning",
                message=f"Сетевая ошибка при генерации изображения: {exc}",
            )
            raise ImageGenerationError("Сетевая ошибка при генерации изображения") from exc
        except APIError as exc:
            # Обработка других ошибок API
            self.log_event(
                event="image_generation_failed",
                user_id=user_id_str,
                status="api_error",
                level="error",
                message=f"Ошибка API при генерации изображения: {exc}",
            )
            raise ImageGenerationError(f"Ошибка API при генерации изображения: {exc}") from exc
        except ClientError as exc:
            # Общая обработка ошибок клиента
            self.log_event(
                event="image_generation_failed",
                user_id=user_id_str,
                status="client_error",
                level="error",
                message=f"Ошибка клиента при генерации изображения: {exc}",
            )
            raise ImageGenerationError("Ошибка клиента при генерации изображения") from exc
        except Exception as e:
            self.logger.error(f"Ошибка при генерации изображения: {e}", exc_info=True)
            raise ImageGenerationError(f"Ошибка при генерации изображения: {e}") from e
