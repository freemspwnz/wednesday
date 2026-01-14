"""Фабрики для создания ML‑клиентов (изображения и текст).

Эти функции не знают о Telegram‑боте или PTB. Они работают только с:

- `ClientManagementService`;
- конфигурацией (`Config`);
- HTTP‑сессией и логгером.

Регистрация клиентов в контейнерах (`get_image_client_container`,
`get_text_client_container`) остаётся здесь, чтобы не тянуть детали
во внешний DI‑контейнер.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infra.clients.client_manager import ClientManagementService
from infra.clients.image_client_container import get_image_client_container
from infra.clients.text_client_container import get_text_client_container
from shared.config import Config
from shared.protocols.clients import ITextToImageClient, ITextToTextClient
from shared.protocols.infrastructure import ILogger
from shared.protocols.repositories import IModelsRepo

if TYPE_CHECKING:
    import aiohttp


def build_client_management_service(
    *,
    models_repo: IModelsRepo,
    logger: ILogger,
) -> ClientManagementService:
    """Создаёт `ClientManagementService` для управления ML‑клиентами."""
    return ClientManagementService(
        models_repo=models_repo,
        logger=logger,
    )


def build_image_client(
    *,
    client_manager: ClientManagementService,
    models_repo: IModelsRepo,
    config: Config,
    http_session: aiohttp.ClientSession,
    logger: ILogger,
) -> ITextToImageClient:
    """Создаёт и регистрирует клиент для генерации изображений.

    Args:
        client_manager: Сервис управления клиентами.
        models_repo: Репозиторий моделей.
        config: Общая конфигурация приложения.
        http_session: HTTP‑сессия для запросов к ML‑сервисам.
        logger: Логгер для логирования операций.
    """
    log = logger.bind(module="ImageClient")
    log.debug(
        "Создание клиента для генерации изображений",
        event="container_create_image_client",
        status="started",
    )

    kandinsky_config = config.kandinsky
    image_client = client_manager.create_image_client(
        config=kandinsky_config,
        models_repo=models_repo,
        session=http_session,
        logger=logger,
    )

    image_container = get_image_client_container()
    image_container.set_initial_client(image_client)

    log.debug(
        "Клиент для генерации изображений создан",
        event="container_image_client_created",
        status="ok",
    )
    return image_container


def build_text_client(
    *,
    client_manager: ClientManagementService,
    models_repo: IModelsRepo,
    config: Config,
    http_session: aiohttp.ClientSession,
    logger: ILogger,
) -> ITextToTextClient | None:
    """Создаёт и регистрирует клиент для генерации текста (если настроен).

    Args:
        client_manager: Сервис управления клиентами.
        models_repo: Репозиторий моделей.
        config: Общая конфигурация приложения.
        http_session: HTTP‑сессия для запросов к ML‑сервисам.
        logger: Логгер для логирования операций.
    """
    log = logger.bind(module="TextClient")
    gigachat_config = config.gigachat

    if not gigachat_config.authorization_key:
        log.debug(
            "GigaChat не настроен, текстовый клиент не создан",
            event="container_text_client_skipped",
            status="ok",
        )
        return None

    log.debug(
        "Создание клиента для генерации текста",
        event="container_create_text_client",
        status="started",
    )

    text_client = client_manager.create_text_client(
        config=gigachat_config,
        models_repo=models_repo,
        session=http_session,
        logger=logger,
    )

    if text_client is None:
        log.debug(
            "Не удалось создать клиент для генерации текста",
            event="container_text_client_failed",
            status="ok",
        )
        return None

    text_container_instance = get_text_client_container()
    text_container_instance.set_initial_client(text_client)

    log.debug(
        "Клиент для генерации текста создан",
        event="container_text_client_created",
        status="ok",
    )
    return text_container_instance


def create_ml_clients(
    *,
    models_repo: IModelsRepo,
    config: Config,
    http_session: aiohttp.ClientSession,
    logger: ILogger,
) -> tuple[ITextToImageClient, ITextToTextClient | None]:
    """Создаёт ML‑клиентов (изображения и текст) и регистрирует их в контейнерах.

    Возвращает кортеж из:
    - контейнера образов (`ITextToImageClient`);
    - контейнера текста (`ITextToTextClient | None`).
    """
    client_manager = build_client_management_service(
        models_repo=models_repo,
        logger=logger,
    )
    image_client = build_image_client(
        client_manager=client_manager,
        models_repo=models_repo,
        config=config,
        http_session=http_session,
        logger=logger,
    )
    text_client = build_text_client(
        client_manager=client_manager,
        models_repo=models_repo,
        config=config,
        http_session=http_session,
        logger=logger,
    )
    return (image_client, text_client)
