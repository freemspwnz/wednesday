"""
Динамический контейнер для текстового ML‑клиента (`ITextToTextClient`).

Основная задача этого модуля — предоставить **одну точку доступа** к текущему
текстовому клиенту бота (LLM) и поддержку runtime-замены клиентов без рестарта бота.

Клиенты создаются через Dependency Injection в `infra.container._create_clients()`
с использованием `ClientManagementService`.

Для runtime-замены используйте:
    await container.replace_client(
        config=new_config,
        client_manager=client_manager,
    )

Все клиенты требуют конфиг, поэтому метод принимает конфиг и создаёт клиент внутри.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

import aiohttp

from infra.clients.client_manager import ClientManagementService
from infra.logging.logger import get_logger
from shared.config import GigaChatConfig
from shared.models import APIStatusResult, SetModelResult
from shared.protocols.clients import ITextToTextClient
from shared.protocols.infrastructure import ILogger
from shared.protocols.repositories import IModelsRepo

logger = get_logger(__name__)


class TextClientContainer(ITextToTextClient):
    """
    Контейнер‑прокси для текущего активного `ITextToTextClient`.

    Экземпляр этого класса выступает *стабильной* зависимостью для сервисов:
    внутри контейнера можно безопасно менять реальный клиент (GigaChat, другой
    LLM и т.п.), а сами сервисы продолжают работать с одной и той же ссылкой.

    Важно:
    - контейнер сам не создаёт клиентов; начальный клиент инициализируется
      через фабрику `infrastructure.clients.factory.create_text_client()`;
    - замена клиента в рантайме выполняется через `replace_client()`, который
      корректно вызывает `aclose()` у старого клиента (если он реализован);
    - если клиент не инициализирован, методы интерфейса возвращают безопасные
      значения по умолчанию и логируют предупреждение (это покрывает кейс,
      когда GIGACHAT_AUTHORIZATION_KEY не задан).
    """

    def __init__(self, initial_client: ITextToTextClient | None = None) -> None:
        self._client: ITextToTextClient | None = initial_client
        # Блокировка для атомарной замены клиента и закрытия старого.
        self._lock = asyncio.Lock()
        self._logger = logger.bind(component="TextClientContainer")

    # ------------------------------------------------------------------ #
    # Публичный API контейнера                                           #
    # ------------------------------------------------------------------ #

    def get_client(self) -> ITextToTextClient | None:
        """Возвращает текущий активный клиент.

        Returns:
            Текущий активный клиент, реализующий ITextToTextClient, или None
            если клиент не инициализирован.
        """
        return self._client

    def set_initial_client(self, client: ITextToTextClient | None) -> None:
        """
        Устанавливает начальный клиент **синхронно** без закрытия предыдущего.

        Используется только на старте приложения из фабрики, где гарантируется,
        что раньше клиента не было. Для последующих замен в рантайме следует
        использовать асинхронный метод `replace_client()`.
        """
        if self._client is not None or client is None:
            # Ничего не делаем, если клиент уже установлен или новый равен None.
            return

        self._client = client
        self._logger.info(
            "Инициализирован начальный текстовый клиент в контейнере",
            client_type=type(client).__name__,
        )

    async def replace_client(
        self,
        config: GigaChatConfig,
        client_manager: ClientManagementService,
        models_repo: IModelsRepo,
        session: aiohttp.ClientSession,
        logger: ILogger,
    ) -> None:
        """Заменяет активный клиент новым, созданным из конфига.

        Все клиенты требуют конфиг для создания, поэтому этот метод принимает
        конфиг и создаёт клиент через ClientManagementService.

        Args:
            config: Конфигурация для нового клиента.
            client_manager: Сервис для создания клиентов.
            models_repo: Репозиторий моделей (обязательный).
            session: HTTP сессия для использования в клиенте (обязательна).
            logger: Логгер для передачи в клиент (обязателен).

        Raises:
            ValueError: Если не удалось создать клиент (например, authorization_key не задан).
        """
        async with self._lock:
            # Создаём новый клиент
            new_client = client_manager.create_text_client(
                config=config,
                models_repo=models_repo,
                session=session,
                logger=logger,
            )

            if new_client is None:
                raise ValueError("Не удалось создать текстовый клиент: authorization_key не задан")

            # Сохраняем старый клиент для закрытия
            old_client: ITextToTextClient | None = self._client
            self._client = new_client

            if new_client is not None:
                self._logger.info(
                    "Активный текстовый клиент заменён",
                    new_client_type=type(new_client).__name__,
                    old_client_type=type(old_client).__name__ if old_client is not None else None,
                )

            # Закрываем старый клиент, если он реализует `aclose()`.
            if old_client is not None and hasattr(old_client, "aclose"):
                try:
                    aclose = old_client.aclose
                    if asyncio.iscoroutinefunction(aclose):
                        await aclose()
                    else:  # pragma: no cover
                        maybe_coro = aclose()
                        if asyncio.iscoroutine(maybe_coro):
                            await maybe_coro
                except Exception as exc:  # pragma: no cover
                    self._logger.warning(
                        "Не удалось корректно закрыть старый текстовый клиент при замене",
                        error=str(exc),
                        old_client_type=type(old_client).__name__,
                    )

    async def aclose(self) -> None:
        """
        Явно закрывает текущий активный клиент (если он инициализирован).

        Может быть вызван при остановке приложения, если требуется гарантированно
        закрыть соединения LLM‑клиента.
        """
        async with self._lock:
            client = self._client
            self._client = None

        if client is not None and hasattr(client, "aclose"):
            try:
                aclose = client.aclose
                if asyncio.iscoroutinefunction(aclose):
                    await aclose()
                else:  # pragma: no cover
                    maybe_coro = aclose()
                    if asyncio.iscoroutine(maybe_coro):
                        await maybe_coro
            except Exception as exc:  # pragma: no cover - защитное логирование
                self._logger.warning(
                    "Не удалось корректно закрыть текстовый клиент при aclose() контейнера",
                    error=str(exc),
                    client_type=type(client).__name__,
                )

    # ------------------------------------------------------------------ #
    # Реализация интерфейса ITextToTextClient (делегирование)           #
    # ------------------------------------------------------------------ #

    async def generate(self, prompt: str, user_id: str | None = None) -> str:
        """Генерирует текстовый ответ по текстовому промпту через текущий активный клиент.

        Проксирует вызов метода generate к текущему активному клиенту.

        Args:
            prompt: Текстовый запрос/инструкция для модели.
            user_id: Идентификатор пользователя для трейсинга и логирования (опционально).

        Returns:
            Сгенерированный текст.

        Raises:
            RuntimeError: Если активный клиент не установлен.
            ValueError: Если API ключи не сконфигурированы.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
            Сгенерированный текст или None при ошибке или отсутствии клиента.

        """
        client = self._client
        if client is None:
            error_msg = "Текстовый клиент не инициализирован"
            self._logger.error(error_msg, prompt_preview=prompt[:50])
            raise RuntimeError(error_msg)
        return await client.generate(prompt, user_id=user_id)

    async def check_api_status(self) -> APIStatusResult:
        """Проверяет статус API и валидность ключа без траты токенов (dry-run).

        Проксирует вызов метода check_api_status к текущему активному клиенту.

        Returns:
            APIStatusResult с информацией о статусе API.

        Raises:
            RuntimeError: Если активный клиент не установлен.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        client = self._client
        if client is None:
            error_msg = "Текстовый клиент не инициализирован (например, не задан GIGACHAT_AUTHORIZATION_KEY)"
            self._logger.error(error_msg)
            raise RuntimeError(error_msg)
        return await client.check_api_status()

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Возвращает список доступных моделей через текущий активный клиент.

        Проксирует вызов метода get_available_models к текущему активному клиенту.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Список доступных моделей или пустой список при ошибке или отсутствии клиента.

        Note:
            Если клиент не инициализирован, логируется предупреждение и возвращается
            пустой список.
        """
        client = self._client
        if client is None:
            self._logger.warning(
                "Вызван get_available_models(), но текстовый клиент не инициализирован (вернём пустой список)",
            )
            return []
        return await client.get_available_models(save_models=save_models)

    async def set_model(self, model_name: str) -> SetModelResult:
        """Устанавливает текущую модель для генерации текста через текущий активный клиент.

        Проксирует вызов метода set_model к текущему активному клиенту.

        Args:
            model_name: Название модели для установки.

        Returns:
            SetModelResult с информацией о результате установки.

        Raises:
            RuntimeError: Если активный клиент не установлен.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
            ValueError: Если модель не найдена.
        """
        client = self._client
        if client is None:
            error_msg = "Текстовый клиент не инициализирован, смена модели невозможна"
            self._logger.error(
                error_msg,
                requested_model=model_name,
            )
            raise RuntimeError(error_msg)
        return await client.set_model(model_name)


@lru_cache(maxsize=1)
def get_text_client_container() -> TextClientContainer:
    """Глобальный singleton-доступ к контейнеру текстового клиента.

    Возвращает глобальный singleton-экземпляр TextClientContainer. При первом
    вызове создаёт новый контейнер, при последующих возвращает тот же экземпляр.

    Returns:
        Глобальный singleton-экземпляр TextClientContainer.

    Note:
        Все сервисы, которым нужен LLM-клиент, должны зависеть от результата
        этой функции (напрямую или через фабрику `create_text_client()`), а не
        создавать `GigaChatTextClient` самостоятельно.
    """
    container = TextClientContainer()
    logger.info("Создан singleton TextClientContainer для текстового LLM‑клиента")
    return container
