"""
Фабрики для создания клиентов внешних ML‑сервисов.

Модуль инкапсулирует выбор конкретных реализаций интерфейсов:

- `ITextToImageClient` — генерация изображений (по умолчанию Kandinsky);
- `ITextToTextClient` — текстовая модель (по умолчанию GigaChat для промптов).

Выбор бэкендов осуществляется через переменные окружения:

- `IMAGE_MODEL_BACKEND` — имя бэкенда для изображений (например, "kandinsky");
- `TEXT_MODEL_BACKEND` — имя бэкенда для текста (например, "gigachat").

Таким образом, `ImageGenerator` и другие сервисы зависят только от протоколов,
а не от конкретных HTTP‑клиентов, что упрощает замену моделей и тестирование.
"""

from __future__ import annotations

import os
from typing import Final

from services.clients import ITextToImageClient, ITextToTextClient
from services.clients.gigachat_text import GigaChatTextClient
from services.clients.kandinsky import KandinskyClient
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_IMAGE_BACKEND: Final[str] = "kandinsky"
DEFAULT_TEXT_BACKEND: Final[str] = "gigachat"


def create_image_client() -> ITextToImageClient:
    """Создаёт клиент генерации изображений в соответствии с `IMAGE_MODEL_BACKEND`.

    Сейчас поддерживается один бэкенд:

    - ``kandinsky`` — клиент `KandinskyClient` (по умолчанию).

    При неизвестном значении переменной окружения логируем предупреждение и
    возвращаем `KandinskyClient` как безопасный дефолт.
    """
    backend = os.getenv("IMAGE_MODEL_BACKEND", DEFAULT_IMAGE_BACKEND).lower()
    if backend != "kandinsky":
        logger.warning(
            "Неизвестный IMAGE_MODEL_BACKEND=%r, будет использован kandinsky",
            backend,
        )
    return KandinskyClient()


def create_text_client() -> ITextToTextClient | None:
    """Создаёт клиент текстовой модели в соответствии с `TEXT_MODEL_BACKEND`.

    Поддерживаемые значения:

    - ``gigachat`` — клиент `GigaChatTextClient` (дефолт).

    При неизвестном значении логируем предупреждение и возвращаем GigaChat,
    так как он является основным и наиболее ожидаемым бэкендом в текущей
    архитектуре бота.
    """
    from utils.config import config

    backend = os.getenv("TEXT_MODEL_BACKEND", DEFAULT_TEXT_BACKEND).lower()
    if backend not in {"gigachat", ""}:
        logger.warning(
            "Неизвестный TEXT_MODEL_BACKEND=%r, будет использован gigachat",
            backend,
        )
    return GigaChatTextClient(
        auth_url=config.gigachat_auth_url,
        api_url=config.gigachat_api_url,
        authorization_key=config.gigachat_authorization_key,
        scope=config.gigachat_scope,
        model=config.gigachat_model,
        verify_ssl=config.gigachat_verify_ssl,
    )
