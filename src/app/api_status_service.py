"""Сервис для проверки статуса API клиентов."""

from __future__ import annotations

from dataclasses import dataclass

from shared.base.base_service import BaseService
from shared.protocols import IModelsRepo, ITextToImageClient, ITextToTextClient


@dataclass
class ImageAPIStatus:
    """Статус API для генерации изображений."""

    is_available: bool
    status_message: str
    available_models: list[str]
    current_model_id: str | None
    current_model_name: str | None

    @classmethod
    def unavailable(cls, error_message: str) -> ImageAPIStatus:
        """Создаёт статус недоступного API."""
        return cls(
            is_available=False,
            status_message=error_message,
            available_models=[],
            current_model_id=None,
            current_model_name=None,
        )


@dataclass
class TextAPIStatus:
    """Статус API для генерации текста."""

    is_available: bool
    status_message: str
    available_models: list[str]
    current_model: str | None

    @classmethod
    def unavailable(cls, error_message: str) -> TextAPIStatus:
        """Создаёт статус недоступного API."""
        return cls(
            is_available=False,
            status_message=error_message,
            available_models=[],
            current_model=None,
        )


class APIStatusService(BaseService):
    """Сервис для проверки статуса API клиентов.

    Инкапсулирует логику проверки статуса различных API (Kandinsky, GigaChat)
    и предоставляет единый интерфейс для получения статуса.
    """

    MAX_ERROR_DETAILS_LENGTH = 100

    def __init__(
        self,
        image_client: ITextToImageClient | None = None,
        text_client: ITextToTextClient | None = None,
        models_store: IModelsRepo | None = None,
    ) -> None:
        """Инициализирует сервис проверки статуса API.

        Args:
            image_client: Клиент для генерации изображений (опционально).
            text_client: Клиент для генерации текста (опционально).
            models_store: Хранилище моделей для сохранения списков (опционально).
        """
        super().__init__()
        self._image_client = image_client
        self._text_client = text_client
        self._models_store = models_store

    async def check_image_api_status(
        self,
        save_models: bool = True,
    ) -> ImageAPIStatus:
        """Проверяет статус API для генерации изображений.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Статус API для генерации изображений.
        """
        if not self._image_client:
            return ImageAPIStatus.unavailable("⚠️ Клиент не настроен")

        try:
            result = await self._image_client.check_api_status(save_models=save_models)

            # Сохраняем модели в хранилище, если доступно
            if self._models_store is not None and result.models:
                try:
                    await self._models_store.set_kandinsky_available_models(result.models)
                except Exception as store_error:
                    self.logger.warning(f"Не удалось сохранить список моделей Kandinsky: {store_error}")

            return ImageAPIStatus(
                is_available=result.is_available,
                status_message=result.message,
                available_models=result.models,
                current_model_id=result.current_model_id,
                current_model_name=result.current_model_name,
            )
        except Exception as e:
            error_message = f"❌ Ошибка: {str(e)[: self.MAX_ERROR_DETAILS_LENGTH]}"
            self.logger.error(f"Ошибка при проверке API Kandinsky: {e}", exc_info=True)
            return ImageAPIStatus.unavailable(error_message)

    async def check_text_api_status(
        self,
        save_models: bool = True,
    ) -> TextAPIStatus:
        """Проверяет статус API для генерации текста.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Статус API для генерации текста.
        """
        if not self._text_client:
            return TextAPIStatus.unavailable("⚠️ Не настроен (GIGACHAT_AUTHORIZATION_KEY не указан)")

        try:
            result = await self._text_client.check_api_status()

            # Получаем доступные модели
            gigachat_models = await self._text_client.get_available_models(save_models=save_models)

            # Сохраняем модели в хранилище, если доступно
            if self._models_store is not None and gigachat_models:
                try:
                    await self._models_store.set_gigachat_available_models(gigachat_models)
                except Exception as store_error:
                    self.logger.warning(f"Не удалось сохранить список моделей GigaChat: {store_error}")

            # Получаем текущую модель
            current_model: str | None = None
            if self._models_store is not None:
                try:
                    current_model = await self._models_store.get_gigachat_model() or "GigaChat"
                except Exception:
                    pass

            return TextAPIStatus(
                is_available=result.is_available,
                status_message=result.message,
                available_models=gigachat_models,
                current_model=current_model or result.current_model_name,
            )
        except Exception as e:
            error_message = f"❌ Ошибка: {str(e)[: self.MAX_ERROR_DETAILS_LENGTH]}"
            self.logger.error(f"Ошибка при проверке GigaChat API: {e}", exc_info=True)
            return TextAPIStatus.unavailable(error_message)

    async def get_image_models(
        self,
        save_models: bool = True,
    ) -> list[str]:
        """Получает список доступных моделей для генерации изображений.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список моделей.

        Returns:
            Список доступных моделей.
        """
        if not self._image_client:
            return []

        try:
            return await self._image_client.get_available_models(save_models=save_models)
        except Exception as e:
            self.logger.error(f"Ошибка при получении моделей Kandinsky: {e}", exc_info=True)
            return []

    async def get_text_models(
        self,
        save_models: bool = True,
    ) -> list[str]:
        """Получает список доступных моделей для генерации текста.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список моделей.

        Returns:
            Список доступных моделей.
        """
        if not self._text_client:
            return []

        try:
            return await self._text_client.get_available_models(save_models=save_models)
        except Exception as e:
            self.logger.error(f"Ошибка при получении моделей GigaChat: {e}", exc_info=True)
            return []
