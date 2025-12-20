"""Протоколы для зависимостей сервисов."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from services.clients.models.status import APIStatusResult, SetModelResult
    from services.infrastructure.repositories import ImageRecord, PromptRecord


@runtime_checkable
class IMetrics(Protocol):
    """Протокол для системы метрик."""

    async def increment_generation_success(self) -> None:
        """Увеличивает счётчик успешных генераций изображений."""
        ...

    async def increment_generation_failed(self) -> None:
        """Увеличивает счётчик неудачных генераций изображений."""
        ...

    async def increment_cache_hit(self) -> None:
        """Увеличивает счётчик попаданий в кэш."""
        ...

    async def increment_dispatch_success(self) -> None:
        """Увеличивает счётчик успешных отправок сообщений."""
        ...

    async def increment_dispatch_failed(self) -> None:
        """Увеличивает счётчик неудачных отправок сообщений."""
        ...

    async def record_circuit_breaker_trip(self) -> None:
        """Увеличивает счётчик срабатываний circuit breaker."""
        ...

    async def get_summary(self) -> dict[str, Any]:
        """Возвращает сводку всех метрик производительности.

        Returns:
            Словарь с ключами:
            - generations_total: общее количество генераций
            - generations_success: количество успешных генераций
            - generations_failed: количество неудачных генераций
            - generations_retries: количество повторных попыток
            - average_generation_time: среднее время генерации в секундах (строка)
            - dispatches_success: количество успешных отправок
            - dispatches_failed: количество неудачных отправок
            - circuit_breaker_trips: количество срабатываний circuit breaker
        """
        ...


@runtime_checkable
class ICircuitBreaker(Protocol):
    """Протокол для circuit breaker."""

    async def is_open(self) -> bool:
        """Возвращает True, если circuit breaker открыт и запросы должны блокироваться."""
        ...

    async def record_success(self) -> None:
        """Регистрирует успешный запрос и, при необходимости, сбрасывает счётчик ошибок."""
        ...

    async def record_failure(self) -> None:
        """Регистрирует неудачу и обновляет состояние circuit breaker."""
        ...


@runtime_checkable
class IRateLimiter(Protocol):
    """Протокол для сервиса rate limiting."""

    async def is_allowed(self, key: str) -> bool:
        """Возвращает True, если запрос разрешён и инкрементирует счётчик по ключу."""
        ...

    async def reset(self, key: str) -> None:
        """Сбрасывает счётчик по ключу."""
        ...


@runtime_checkable
class IImageStorage(Protocol):
    """Протокол для файлового хранилища изображений."""

    async def save(self, data: bytes, folder: str | None = None, prefix: str = "frog") -> str:
        """Сохраняет байтовые данные изображения в файловое хранилище.

        Args:
            data: Данные для сохранения (байты).
            folder: Папка для сохранения.
            prefix: Префикс имени файла.

        Returns:
            Путь к сохранённому файлу.
        """
        ...

    async def get_random(self, folder: str | None = None) -> tuple[bytes, str] | None:
        """Получает случайный файл изображения из папки.

        Args:
            folder: Папка для поиска файла.

        Returns:
            Кортеж (данные файла, путь к файлу) или None, если файлы не найдены.
        """
        ...


T = TypeVar("T")


@runtime_checkable
class ICache(Protocol[T]):
    """Протокол для кэширования данных."""

    async def get(self, key: str) -> T | None:
        """Получает значение из кэша по ключу.

        Args:
            key: Ключ для получения значения.

        Returns:
            Значение из кэша или None, если ключ не найден.
        """
        ...

    async def set(self, key: str, value: T, ttl: int | None = None) -> None:
        """Сохраняет значение в кэш.

        Args:
            key: Ключ для сохранения.
            value: Значение для сохранения.
            ttl: Время жизни записи в секундах (опционально).
        """
        ...

    async def delete(self, key: str) -> None:
        """Удаляет значение из кэша.

        Args:
            key: Ключ для удаления.
        """
        ...


@runtime_checkable
class ITaskQueue(Protocol):
    """Протокол для отправки задач в очередь выполнения.

    Абстрагирует детали реализации очереди задач (Celery, Redis Streams, и т.д.)
    от application-сервисов.
    """

    async def send_frog_manual_task(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
    ) -> None:
        """Ставит задачу генерации и отправки жабы в очередь.

        Args:
            chat_id: ID чата для отправки изображения.
            user_id: ID пользователя, запросившего генерацию.
            status_message_id: ID статусного сообщения для удаления после отправки (опционально).

        Raises:
            Exception: При ошибке постановки задачи в очередь.
        """
        ...


@runtime_checkable
class IImageRepo(Protocol):
    """Протокол для репозитория изображений в БД."""

    async def get_by_prompt_hash(self, prompt_hash: str) -> ImageRecord | None:
        """Получает изображение по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            ImageRecord если изображение найдено, None иначе.
        """
        ...

    async def load_image_bytes(self, image_record: ImageRecord) -> bytes:
        """Загружает байты изображения из файла по ImageRecord (асинхронно).

        Args:
            image_record: Запись ImageRecord с метаданными изображения.

        Returns:
            Байты изображения из файла.

        Raises:
            FileNotFoundError: Если файл изображения не найден на диске.
            OSError: При ошибке чтения файла.
        """
        ...

    async def get_or_create_image(
        self,
        prompt_hash: str,
        image_bytes: bytes,
    ) -> ImageRecord:
        """Создает или получает существующее изображение.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.
            image_bytes: Байты изображения для сохранения.

        Returns:
            ImageRecord с метаданными изображения (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных или файловой системе.
        """
        ...


@runtime_checkable
class IPromptRepo(Protocol):
    """Протокол для репозитория промптов в БД."""

    async def get_or_create_prompt(self, prompt_text: str) -> PromptRecord:
        """Создает или получает существующий промпт.

        Args:
            prompt_text: Исходный текст промпта.

        Returns:
            PromptRecord с метаданными промпта (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        ...

    async def get_prompt_by_hash(self, prompt_hash: str) -> PromptRecord | None:
        """Получает промпт по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            PromptRecord если промпт найден, None иначе.
        """
        ...


@runtime_checkable
class IUsageTracker(Protocol):
    """Протокол для трекера использования генераций изображений."""

    async def increment(
        self,
        count: int = 1,
        when: datetime | None = None,
    ) -> int:
        """Увеличивает счётчик генераций за месяц и возвращает новое значение.

        Args:
            count: Количество генераций для добавления (по умолчанию 1).
            when: Дата для учёта генераций. Если не указана, используется текущая дата UTC.

        Returns:
            Новое значение счётчика генераций за месяц.
        """
        ...

    async def get_limits_info(
        self,
        when: datetime | None = None,
    ) -> tuple[int, int, int]:
        """Возвращает информацию о лимитах использования для месяца.

        Args:
            when: Дата для получения информации. Если не указана, используется текущая дата UTC.

        Returns:
            Кортеж (total, frog_threshold, monthly_quota), где:
            - total: текущее количество использованных генераций
            - frog_threshold: порог для ручных генераций /frog
            - monthly_quota: месячная квота генераций
        """
        ...

    async def can_use_frog(self, when: datetime | None = None) -> bool:
        """Проверяет, не превышен ли порог ручных /frog для месяца.

        Args:
            when: Дата для проверки. Если не указана, используется текущая дата UTC.

        Returns:
            True если можно использовать команду /frog (не превышен порог),
            False иначе.
        """
        ...

    async def set_frog_threshold(self, threshold: int) -> int:
        """Устанавливает порог ручных генераций (/frog).

        Args:
            threshold: Новое значение порога для ручных генераций.

        Returns:
            Установленное значение порога (после ограничения диапазоном).
        """
        ...

    async def set_month_total(self, total: int, when: datetime | None = None) -> int:
        """Устанавливает текущее значение использования за месяц в абсолютном виде.

        Args:
            total: Абсолютное значение счётчика генераций для установки.
            when: Дата для установки значения. Если не указана, используется текущая дата UTC.

        Returns:
            Установленное значение счётчика.
        """
        ...

    @property
    def monthly_quota(self) -> int:
        """Возвращает месячную квоту генераций."""
        ...


@runtime_checkable
class IChatsRepo(Protocol):
    """Протокол для репозитория чатов в БД."""

    async def list_chat_ids(self) -> list[int]:
        """Возвращает список ID всех зарегистрированных чатов.

        Returns:
            Список идентификаторов чатов, отсортированный по chat_id.
        """
        ...

    async def add_chat(self, chat_id: int, title: str | None = None) -> None:
        """Добавляет или обновляет чат в списке рассылки.

        Args:
            chat_id: Идентификатор чата для добавления или обновления.
            title: Название чата. Если не указано, используется пустая строка.
        """
        ...

    async def remove_chat(self, chat_id: int) -> None:
        """Удаляет чат из списка рассылки.

        Args:
            chat_id: Идентификатор чата для удаления.
        """
        ...


@runtime_checkable
class IModelsRepo(Protocol):
    """Протокол для репозитория моделей Kandinsky и GigaChat."""

    async def set_kandinsky_model(self, pipeline_id: str, pipeline_name: str) -> None:
        """Устанавливает текущую модель Kandinsky.

        Args:
            pipeline_id: Идентификатор pipeline модели Kandinsky.
            pipeline_name: Название pipeline модели Kandinsky.
        """
        ...

    async def get_kandinsky_model(self) -> tuple[str | None, str | None]:
        """Возвращает текущую модель Kandinsky.

        Returns:
            Кортеж (pipeline_id, pipeline_name) текущей модели Kandinsky.
            Если модель не установлена, возвращает (None, None).
        """
        ...

    async def set_gigachat_model(self, model_name: str) -> None:
        """Устанавливает текущую модель GigaChat.

        Args:
            model_name: Название модели GigaChat для установки.
        """
        ...

    async def get_gigachat_model(self) -> str | None:
        """Возвращает текущую модель GigaChat.

        Returns:
            Название текущей модели GigaChat или None, если модель не установлена.
        """
        ...

    async def set_kandinsky_available_models(self, models: list[dict[str, Any]] | list[str]) -> None:
        """Сохраняет список доступных моделей Kandinsky.

        Args:
            models: Список моделей. Может быть списком словарей с полями
                'id' и 'name' или списком строк.
        """
        ...

    async def get_kandinsky_available_models(self) -> list[str]:
        """Возвращает список доступных моделей Kandinsky.

        Returns:
            Список строк моделей в формате "Name (ID: xxx)".
            Если модели не установлены, возвращает пустой список.
        """
        ...

    async def set_gigachat_available_models(self, models: list[str]) -> None:
        """Сохраняет список доступных моделей GigaChat.

        Args:
            models: Список названий моделей GigaChat.
        """
        ...

    async def get_gigachat_available_models(self) -> list[str]:
        """Возвращает список доступных моделей GigaChat.

        Returns:
            Список названий моделей GigaChat.
            Если модели не установлены, возвращает пустой список.
        """
        ...


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
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """

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
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """

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
