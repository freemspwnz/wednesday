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
from services.clients.image_client_container import get_image_client_container
from services.clients.kandinsky import KandinskyClient
from services.clients.text_client_container import get_text_client_container
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_IMAGE_BACKEND: Final[str] = "kandinsky"
DEFAULT_TEXT_BACKEND: Final[str] = "gigachat"


def create_image_client() -> ITextToImageClient:
    """Создаёт/возвращает контейнер клиента генерации изображений.

    Фабрика создаёт и возвращает контейнер клиента генерации изображений в соответствии
    с переменной окружения `IMAGE_MODEL_BACKEND`. Контейнер реализует интерфейс
    `ITextToImageClient` и проксирует вызовы к текущему активному клиенту.

    Returns:
        Экземпляр ImageClientContainer, реализующий интерфейс ITextToImageClient.

    Note:
        - Фабрика возвращает глобальный singleton-контейнер, который можно безопасно
          использовать во всех сервисах.
        - Все сервисы должны зависеть от результата этой функции и вызывать методы
          интерфейса (`generate`) на контейнере.
        - В будущем админ-команды смогут заменить реальный клиент внутри контейнера
          без рестарта бота (через `replace_client()`).

    Поддерживаемые значения `IMAGE_MODEL_BACKEND`:
        - ``kandinsky`` (или пустое значение) — клиент `KandinskyClient`.

    При неизвестном значении логируется предупреждение и используется Kandinsky
    как безопасный дефолт.
    """
    backend = os.getenv("IMAGE_MODEL_BACKEND", DEFAULT_IMAGE_BACKEND).lower()
    if backend != "kandinsky":
        logger.warning(
            f"Неизвестный IMAGE_MODEL_BACKEND={backend!r}, будет использован kandinsky",
        )

    # Создаём реальный HTTP‑клиент один раз и регистрируем его в singleton‑контейнере.
    # Контейнер реализует интерфейс `ITextToImageClient`, так что вызывающий код
    # продолжает работать через те же методы (`generate`),
    # но теперь с возможностью безопасной замены клиента в рантайме.
    kandinsky_client = KandinskyClient()

    container = get_image_client_container()
    # Инициализируем контейнер только один раз; последующие вызовы фабрики
    # вернут тот же контейнер без повторной замены клиента.
    container.set_initial_client(kandinsky_client)
    return container


def create_text_client() -> ITextToTextClient | None:
    """Создаёт/возвращает контейнер текстовой модели.

    Фабрика создаёт и возвращает контейнер текстового клиента в соответствии с
    переменной окружения `TEXT_MODEL_BACKEND`. Контейнер реализует интерфейс
    `ITextToTextClient` и проксирует вызовы к текущему активному клиенту.

    Returns:
        Экземпляр TextClientContainer, реализующий интерфейс ITextToTextClient, или None
        если текстовый клиент не настроен (например, отсутствует GIGACHAT_AUTHORIZATION_KEY).

    Note:
        - Фабрика возвращает глобальный singleton-контейнер, который можно безопасно
          использовать во всех сервисах.
        - Все сервисы должны зависеть от результата этой функции и вызывать методы
          интерфейса (`generate`, `set_model`, `get_available_models`) на контейнере.
        - В будущем админ-команды смогут заменить реальный клиент внутри контейнера
          без рестарта бота (через `replace_client()`).

    Поддерживаемые значения `TEXT_MODEL_BACKEND`:
        - ``gigachat`` (или пустое значение) — клиент `GigaChatTextClient`.

    При неизвестном значении логируется предупреждение и используется GigaChat
    как безопасный дефолт.
    """
    from utils.config import config

    backend = os.getenv("TEXT_MODEL_BACKEND", DEFAULT_TEXT_BACKEND).lower()
    if backend not in {"gigachat", ""}:
        logger.warning(
            f"Неизвестный TEXT_MODEL_BACKEND={backend!r}, будет использован gigachat",
        )

    # Создаём реальный HTTP‑клиент один раз и регистрируем его в singleton‑контейнере.
    # Контейнер реализует интерфейс `ITextToTextClient`, так что вызывающий код
    # продолжает работать через те же методы (`generate`, `set_model` и т.д.),
    # но теперь с возможностью безопасной замены клиента в рантайме.
    gigachat_client = GigaChatTextClient(
        auth_url=config.gigachat_auth_url,
        api_url=config.gigachat_api_url,
        authorization_key=config.gigachat_authorization_key,
        scope=config.gigachat_scope,
        model=config.gigachat_model,
        verify_ssl=config.gigachat_verify_ssl,
    )

    container = get_text_client_container()
    # Инициализируем контейнер только один раз; последующие вызовы фабрики
    # вернут тот же контейнер без повторной замены клиента.
    container.set_initial_client(gigachat_client)
    return container
