"""Доменный сервис для генерации изображений.

Содержит чистую логику генерации изображений без зависимостей от инфраструктуры
(кэш, метрики, circuit breaker, файловое хранилище).
"""

from __future__ import annotations

from domain.value_objects import Prompt
from shared.base.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    ImageGenerationError,
    NetworkError,
    UnexpectedImageGenerationError,
)
from shared.protocols import ITextToImageClient


class ImageGenerationService:
    """Доменный сервис для генерации изображений.

    Выполняет валидацию и нормализацию промптов через Value Object Prompt,
    затем чистую генерацию изображений через ITextToImageClient без зависимостей
    от инфраструктуры (кэш, метрики, circuit breaker).

    Валидация и нормализация промптов инкапсулированы в Value Object Prompt.
    """

    def __init__(self, image_client: ITextToImageClient) -> None:
        """Инициализирует сервис генерации изображений.

        Args:
            image_client: Клиент для генерации изображений по текстовому промпту.
        """
        self._image_client = image_client

    async def generate(
        self,
        prompt: str,
        user_id: int | None = None,
    ) -> bytes:
        """Генерирует изображение по промпту.

        Выполняет валидацию и нормализацию промпта через Value Object Prompt,
        затем чистую генерацию через ITextToImageClient без кэширования, метрик
        и других инфраструктурных зависимостей.

        Retry логика применяется на уровне клиента (ITextToImageClient).

        Args:
            prompt: Текстовый промпт для генерации изображения.
            user_id: Идентификатор пользователя для логирования (опционально).

        Returns:
            Байты изображения.

        Raises:
            ImageGenerationError: При невалидном промпте или критических ошибках генерации.
        """
        try:
            validated_prompt = Prompt(prompt)
        except ValueError as e:
            raise ImageGenerationError(f"Невалидный промпт: {e}") from e

        try:
            user_id_str = str(user_id) if user_id is not None else None
            image_data = await self._image_client.generate(validated_prompt.value, user_id=user_id_str)
            return image_data

        except AuthenticationError as exc:
            raise ImageGenerationError("Ошибка аутентификации при генерации изображения") from exc
        except NetworkError as exc:
            raise ImageGenerationError("Сетевая ошибка при генерации изображения") from exc
        except APIError as exc:
            raise ImageGenerationError(f"Ошибка API при генерации изображения: {exc}") from exc
        except ClientError as exc:
            raise ImageGenerationError("Ошибка клиента при генерации изображения") from exc
        except (MemoryError, SystemExit, KeyboardInterrupt):
            # Системные ошибки пробрасываем без обработки
            raise
        except Exception as exc:
            # Явно помечаем как неожиданный сценарий
            raise UnexpectedImageGenerationError(f"Неожиданная ошибка при генерации изображения: {exc}") from exc
