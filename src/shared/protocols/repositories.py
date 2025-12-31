"""Протоколы репозиториев для работы с базой данных."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import asyncpg

    from shared.models import ImageRecordDTO, PromptRecordDTO
else:
    import asyncpg


@runtime_checkable
class IImageRepo(Protocol):
    """Протокол для репозитория изображений в БД."""

    async def get_by_prompt_hash(self, prompt_hash: str) -> ImageRecordDTO | None:
        """Получает изображение по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            ImageRecordDTO если изображение найдено, None иначе.
        """
        ...

    async def load_image_bytes(self, image_record: ImageRecordDTO) -> bytes:
        """Загружает байты изображения из файла по ImageRecordDTO (асинхронно).

        Args:
            image_record: Запись ImageRecordDTO с метаданными изображения.

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
    ) -> ImageRecordDTO:
        """Создает или получает существующее изображение.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.
            image_bytes: Байты изображения для сохранения.

        Returns:
            ImageRecordDTO с метаданными изображения (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных или файловой системе.
        """
        ...


@runtime_checkable
class IPromptRepo(Protocol):
    """Протокол для репозитория промптов в БД."""

    async def get_or_create_prompt(self, prompt_text: str) -> PromptRecordDTO:
        """Создает или получает существующий промпт.

        Args:
            prompt_text: Исходный текст промпта.

        Returns:
            PromptRecordDTO с метаданными промпта (существующая или новая запись).

        Raises:
            RuntimeError: При крайне маловероятной ошибке конкурентной вставки.
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        ...

    async def get_prompt_by_hash(self, prompt_hash: str) -> PromptRecordDTO | None:
        """Получает промпт по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            PromptRecordDTO если промпт найден, None иначе.
        """
        ...


@runtime_checkable
class IUsageTracker(Protocol):
    """Протокол для трекера использования генераций изображений."""

    async def increment(
        self,
        connection: asyncpg.Connection,
        count: int = 1,
        when: datetime | None = None,
    ) -> int:
        """Увеличивает счётчик генераций за месяц и возвращает новое значение.

        Args:
            connection: Соединение БД для использования в транзакции (обязательно).
            count: Количество генераций для добавления (по умолчанию 1).
            when: Дата для учёта генераций. Если не указана, используется текущая дата UTC.

        Returns:
            Новое значение счётчика генераций за месяц.
        """
        ...

    async def increment_with_pool(
        self,
        count: int = 1,
        when: datetime | None = None,
    ) -> int:
        """Увеличивает счётчик генераций за месяц, получая connection из pool.

        Helper-метод для использования вне UoW контекста.

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
class IAdminsRepo(Protocol):
    """Протокол для репозитория администраторов."""

    async def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором.

        Args:
            user_id: Идентификатор пользователя для проверки.

        Returns:
            True если пользователь является администратором, False иначе.
        """
        ...

    async def add_admin(self, user_id: int) -> bool:
        """Добавляет администратора.

        Args:
            user_id: Идентификатор пользователя для добавления в администраторы.

        Returns:
            True если администратор был добавлен, False если он уже существовал.
        """
        ...

    async def remove_admin(self, user_id: int) -> bool:
        """Удаляет администратора.

        Args:
            user_id: Идентификатор пользователя для удаления из администраторов.

        Returns:
            True если администратор был удалён, False если он не был администратором.
        """
        ...

    async def list_all_admins(self) -> list[int]:
        """Возвращает список всех администраторов.

        Returns:
            Список идентификаторов всех администраторов.
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
