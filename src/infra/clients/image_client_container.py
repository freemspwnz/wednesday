"""
Динамический контейнер для клиента генерации изображений (`ITextToImageClient`).

Основная задача этого модуля — предоставить **одну точку доступа** к текущему
клиенту генерации изображений (TTI) и подготовить инфраструктуру для будущих
админ‑команд, которые смогут менять бэкенд в рантайме без рестарта бота.

Ключевые идеи:

- контейнер реализует интерфейс `ITextToImageClient` и прозрачно проксирует
  вызовы (`generate`) к текущему активному клиенту;
- все сервисы (бот, генератор изображений и т.п.) должны зависеть от
  контейнера, а не от конкретной реализации (`KandinskyClient`);
- при замене клиента в рантайме старый экземпляр корректно закрывается
  через его асинхронный метод `aclose()` (если он реализован).

Использование (будущее, для админ‑команд):

    from infra.clients.image_client_container import get_image_client_container
    from infra.clients.kandinsky import KandinskyClient

    container = get_image_client_container()

    # Создаём нового клиента (например, другой провайдер TTI)
    new_client = KandinskyClient()

    # Безопасно подменяем активный клиент:
    await container.replace_client(new_client)

    # Все существующие сервисы, которые уже держат ссылку на контейнер,
    # автоматически начнут использовать нового клиента без рестарта процесса.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from infra.clients.models.status import APIStatusResult, SetModelResult
from infra.logging.logger import get_logger
from shared.protocols import ITextToImageClient

logger = get_logger(__name__)


class ImageClientContainer(ITextToImageClient):
    """
    Контейнер‑прокси для текущего активного `ITextToImageClient`.

    Экземпляр этого класса выступает *стабильной* зависимостью для сервисов:
    внутри контейнера можно безопасно менять реальный клиент (Kandinsky, другой
    TTI‑провайдер и т.п.), а сами сервисы продолжают работать с одной и той же ссылкой.

    Важно:
    - контейнер сам не создаёт клиентов; начальный клиент инициализируется
      через фабрику `infrastructure.clients.factory.create_image_client()`;
    - замена клиента в рантайме выполняется через `replace_client()`, который
      корректно вызывает `aclose()` у старого клиента (если он реализован);
    - если клиент не инициализирован, методы интерфейса возвращают безопасные
      значения по умолчанию и логируют предупреждение.
    """

    def __init__(self, initial_client: ITextToImageClient | None = None) -> None:
        self._client: ITextToImageClient | None = initial_client
        # Блокировка для атомарной замены клиента и закрытия старого.
        self._lock = asyncio.Lock()
        self._logger = logger.bind(component="ImageClientContainer")

    # ------------------------------------------------------------------ #
    # Публичный API контейнера                                           #
    # ------------------------------------------------------------------ #

    def get_client(self) -> ITextToImageClient | None:
        """Возвращает текущий активный клиент.

        Returns:
            Текущий активный клиент, реализующий ITextToImageClient, или None
            если клиент не инициализирован.
        """
        return self._client

    def set_initial_client(self, client: ITextToImageClient | None) -> None:
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
            "Инициализирован начальный клиент генерации изображений в контейнере",
            client_type=type(client).__name__,
        )

    async def replace_client(self, client: ITextToImageClient | None) -> None:
        """
        Асинхронно заменяет активный клиент на новый и корректно закрывает старый.

        Этот метод предназначен для будущих админ‑команд, которые смогут в
        рантайме переключать TTI‑бэкенд (например, Kandinsky -> другой провайдер)
        без остановки процесса бота.

        Алгоритм:
        - берём lock, сохраняем ссылку на старый клиент;
        - устанавливаем новый клиент;
        - если у старого есть асинхронный метод `aclose()`, вызываем его;
        - все сервисы, работающие через контейнер, автоматически начнут
          использовать новый клиент.

        Пример использования (для будущих админ‑команд):

            container = get_image_client_container()
            new_client = KandinskyClient()  # или другой ITextToImageClient
            await container.replace_client(new_client)
        """
        async with self._lock:
            old_client: ITextToImageClient | None = self._client
            self._client = client

            if client is not None:
                self._logger.info(
                    "Активный клиент генерации изображений заменён",
                    new_client_type=type(client).__name__,
                    old_client_type=type(old_client).__name__ if old_client is not None else None,
                )

            # Закрываем старый клиент, если он реализует `aclose()`.
            if old_client is not None and hasattr(old_client, "aclose"):
                try:
                    aclose = old_client.aclose
                    if asyncio.iscoroutinefunction(aclose):
                        await aclose()
                    else:  # pragma: no cover - защитный фоллбек для нестандартных реализаций
                        maybe_coro = aclose()
                        if asyncio.iscoroutine(maybe_coro):
                            await maybe_coro
                except Exception as exc:  # pragma: no cover - защитное логирование
                    self._logger.warning(
                        "Не удалось корректно закрыть старый клиент генерации изображений при замене",
                        error=str(exc),
                        old_client_type=type(old_client).__name__,
                    )

    async def aclose(self) -> None:
        """
        Явно закрывает текущий активный клиент (если он инициализирован).

        Может быть вызван при остановке приложения, если требуется гарантированно
        закрыть соединения TTI‑клиента.
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
                    "Не удалось корректно закрыть клиент генерации изображений при aclose() контейнера",
                    error=str(exc),
                    client_type=type(client).__name__,
                )

    # ------------------------------------------------------------------ #
    # Реализация интерфейса ITextToImageClient (делегирование)          #
    # ------------------------------------------------------------------ #

    async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
        """Генерирует изображение по текстовому промпту через текущий активный клиент.

        Проксирует вызов метода generate к текущему активному клиенту.

        Args:
            prompt: Текстовое описание изображения для генерации.
            user_id: Идентификатор пользователя для трейсинга и логирования (опционально).

        Returns:
            Байтовое представление изображения.

        Raises:
            RuntimeError: Если активный клиент не установлен.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).

        """
        client = self._client
        if client is None:
            error_msg = "Клиент генерации изображений не инициализирован"
            self._logger.error(error_msg, prompt_preview=prompt[:50])
            raise RuntimeError(error_msg)
        return await client.generate(prompt, user_id=user_id)

    async def check_api_status(self, save_models: bool = True) -> APIStatusResult:
        """
        Проверяет статус API и валидность ключа без генерации изображения (dry-run).

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

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
            error_msg = "Клиент генерации изображений не инициализирован"
            self._logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Проверяем, есть ли у клиента метод check_api_status
        if not hasattr(client, "check_api_status"):
            error_msg = "Клиент не поддерживает проверку статуса API"
            self._logger.error(error_msg, client_type=type(client).__name__)
            raise RuntimeError(error_msg)

        return await client.check_api_status(save_models=save_models)

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Возвращает список доступных моделей через текущий активный клиент.

        Проксирует вызов метода get_available_models к текущему активному клиенту.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Список доступных моделей или пустой список при ошибке или отсутствии клиента.

        Note:
            Если клиент не инициализирован или не поддерживает метод, логируется
            предупреждение и возвращается пустой список.
        """
        client = self._client
        if client is None:
            self._logger.warning(
                "Вызван get_available_models(), но клиент генерации изображений не инициализирован "
                "(вернём пустой список)",
            )
            return []

        # Проверяем, есть ли у клиента метод get_available_models
        if not hasattr(client, "get_available_models"):
            self._logger.warning(
                "Клиент не поддерживает получение списка моделей",
                client_type=type(client).__name__,
            )
            return []

        return await client.get_available_models(save_models=save_models)

    async def set_model(self, model_identifier: str) -> SetModelResult:
        """Устанавливает текущую модель для генерации изображений через текущий активный клиент.

        Проксирует вызов метода set_model к текущему активному клиенту.

        Args:
            model_identifier: ID модели или название (или часть названия).

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
            error_msg = "Клиент генерации изображений не инициализирован, смена модели невозможна"
            self._logger.error(
                error_msg,
                requested_model=model_identifier,
            )
            raise RuntimeError(error_msg)

        # Проверяем, есть ли у клиента метод set_model
        if not hasattr(client, "set_model"):
            error_msg = "Клиент не поддерживает смену модели"
            self._logger.error(
                error_msg,
                client_type=type(client).__name__,
                requested_model=model_identifier,
            )
            raise RuntimeError(error_msg)

        return await client.set_model(model_identifier)


@lru_cache(maxsize=1)
def get_image_client_container() -> ImageClientContainer:
    """Глобальный singleton-доступ к контейнеру клиента генерации изображений.

    Возвращает глобальный singleton-экземпляр ImageClientContainer. При первом
    вызове создаёт новый контейнер, при последующих возвращает тот же экземпляр.

    Returns:
        Глобальный singleton-экземпляр ImageClientContainer.

    Note:
        Все сервисы, которым нужен TTI-клиент, должны зависеть от результата
        этой функции (напрямую или через фабрику `create_image_client()`), а не
        создавать `KandinskyClient` самостоятельно.
    """
    container = ImageClientContainer()
    logger.info("Создан singleton ImageClientContainer для клиента генерации изображений")
    return container
