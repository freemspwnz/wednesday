"""
Сервис управления клиентами для runtime-замены.

Обеспечивает создание клиентов разных типов с кастомными конфигами
для поддержки runtime-замены без рестарта приложения.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.config import GigaChatConfig, KandinskyConfig
from shared.protocols import ILogger, IModelsRepo, ITextToImageClient, ITextToTextClient

if TYPE_CHECKING:
    import aiohttp


class ClientManagementService:
    """Сервис для создания и управления клиентами ML-сервисов.

    Обеспечивает:
    - Создание клиентов разных типов через DI
    - Поддержку кастомных конфигов при runtime-замене
    - Централизованное управление зависимостями клиентов
    """

    def __init__(
        self,
        models_repo: IModelsRepo,
        logger: ILogger,
    ) -> None:
        """Инициализация сервиса управления клиентами.

        Args:
            models_repo: Репозиторий моделей для передачи в клиенты.
            logger: Логгер для использования (обязателен). Должен быть передан через DI.
        """
        self._models_repo = models_repo
        self._logger = logger.bind(module="ClientManagementService")

    def create_image_client(
        self,
        config: KandinskyConfig,
        models_repo: IModelsRepo,
        session: aiohttp.ClientSession,
        logger: ILogger,
    ) -> ITextToImageClient:
        """Создаёт клиент для генерации изображений.

        Args:
            config: Конфигурация Kandinsky клиента.
            models_repo: Репозиторий моделей (обязательный).
            session: HTTP сессия для использования (обязательна).
            logger: Логгер для передачи в клиент (обязателен).

        Returns:
            Экземпляр KandinskyClient, реализующий ITextToImageClient.
        """
        from infra.clients.kandinsky import KandinskyClient

        client = KandinskyClient(config=config, models_repo=models_repo, session=session, logger=logger)

        self._logger.info(
            "Создан клиент генерации изображений",
            client_type="KandinskyClient",
            base_url=config.base_url,
        )

        return client

    def create_text_client(
        self,
        config: GigaChatConfig,
        models_repo: IModelsRepo,
        session: aiohttp.ClientSession,
        logger: ILogger,
    ) -> ITextToTextClient | None:
        """Создаёт клиент для генерации текста.

        Args:
            config: Конфигурация GigaChat клиента.
            models_repo: Репозиторий моделей (обязательный).
            session: HTTP сессия для использования (обязательна).
            logger: Логгер для передачи в клиент (обязателен).

        Returns:
            Экземпляр GigaChatTextClient, реализующий ITextToTextClient,
            или None если authorization_key не задан.
        """
        if not config.authorization_key:
            self._logger.warning(
                "GigaChat authorization_key не задан, клиент не будет создан",
            )
            return None

        from infra.clients.gigachat_text import GigaChatTextClient

        client = GigaChatTextClient(config=config, models_repo=models_repo, session=session, logger=logger)

        self._logger.info(
            "Создан текстовый клиент",
            client_type="GigaChatTextClient",
            base_url=config.base_url,
        )

        return client
