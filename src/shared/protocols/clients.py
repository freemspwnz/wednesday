"""Протоколы клиентов для внешних API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from shared.models import APIStatusResult, SetModelResult
else:
    # Для runtime импорты не нужны
    pass


@runtime_checkable
class ICaptionProvider(Protocol):
    """Протокол для провайдера подписей."""

    def get_captions(self) -> list[str]:
        """Возвращает список доступных подписей."""
        ...


@runtime_checkable
class ITextToImageClient(Protocol):
    """Интерфейс клиента текст‑к‑изображению.

    Реализация отвечает за обращение к внешнему API и возврат байтов изображения.
    Бизнес‑логика (кеш, метрики, circuit breaker) реализуется поверх этого интерфейса.

    Интерфейс включает методы для управления моделями и проверки статуса API,
    что позволяет унифицировать работу с различными TTI‑провайдерами через контейнер.
    """

    async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
        """Генерирует изображение по текстовому промпту.

        Args:
            prompt: Текстовое описание изображения.
            user_id: Идентификатор пользователя (для трейсинга и логирования), опционально.

        Returns:
            Байтовое представление изображения.

        Raises:
            ValueError: Если API ключи не сконфигурированы.
            shared.base.exceptions.AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            shared.base.exceptions.RateLimitError: Если превышен лимит запросов (429).
            shared.base.exceptions.NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            shared.base.exceptions.APIError: При других ошибках API (4xx, 5xx).
        """
        ...

    async def check_api_status(self, save_models: bool = True) -> APIStatusResult:
        """Проверяет статус API и валидность ключа без генерации изображения (dry-run).

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            APIStatusResult с информацией о статусе API.

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        ...

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Возвращает список доступных моделей.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Список доступных моделей.

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        ...

    async def set_model(self, model_identifier: str) -> SetModelResult:
        """Устанавливает текущую модель для генерации изображений.

        Args:
            model_identifier: ID модели или название (или часть названия).

        Returns:
            SetModelResult с информацией о результате установки.

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
            ValueError: Если модель не найдена.
        """
        ...


@runtime_checkable
class ITextToTextClient(Protocol):
    """Интерфейс клиента текст‑к‑тексту (LLM).

    Реализация отвечает за вызов модели, подготовку/нормализацию ответа
    и возврат итоговой строки без бизнес‑обвязки бота.
    """

    async def generate(self, prompt: str, user_id: str | None = None) -> str:
        """Генерирует текстовый ответ по текстовому промпту.

        Args:
            prompt: Текстовый запрос/инструкция для модели.
            user_id: Идентификатор пользователя (для трейсинга и логирования), опционально.

        Returns:
            Сгенерированный текст.

        Raises:
            ValueError: Если API ключи не сконфигурированы.
            shared.base.exceptions.AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            shared.base.exceptions.RateLimitError: Если превышен лимит запросов (429).
            shared.base.exceptions.NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            shared.base.exceptions.APIError: При других ошибках API (4xx, 5xx).
        """
        ...

    async def check_api_status(self) -> APIStatusResult:
        """Проверяет статус API и валидность ключа без траты токенов (dry-run).

        Returns:
            APIStatusResult с информацией о статусе API.

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        ...

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Возвращает список доступных моделей.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Список доступных моделей.

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        ...

    async def set_model(self, model_name: str) -> SetModelResult:
        """Устанавливает текущую модель для генерации текста.

        Args:
            model_name: Название модели.

        Returns:
            SetModelResult с информацией о результате установки.

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
            ValueError: Если модель не найдена.
        """
        ...
