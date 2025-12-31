"""Application-сервис для управления моделями ML-клиентов.

Инкапсулирует логику выбора и сохранения текущих моделей,
делегируя HTTP-запросы клиентам, а сохранение - репозиторию.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.models import SetModelResult
from shared.protocols.clients import ITextToImageClient, ITextToTextClient
from shared.protocols.infrastructure import ILogger
from shared.protocols.repositories import IModelsRepo


class ModelManagementService(BaseService):
    """Сервис для управления моделями ML-клиентов.

    Отвечает за выбор и сохранение текущих моделей,
    делегируя HTTP-запросы клиентам, а сохранение - репозиторию.
    """

    def __init__(
        self,
        image_client: ITextToImageClient | None,
        text_client: ITextToTextClient | None,
        models_repo: IModelsRepo,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис управления моделями.

        Args:
            image_client: Клиент для генерации изображений (опционально).
            text_client: Клиент для генерации текста (опционально).
            models_repo: Репозиторий моделей для сохранения выбранных моделей.
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._image_client = image_client
        self._text_client = text_client
        self._models_repo = models_repo

    async def set_kandinsky_model(self, model_identifier: str) -> SetModelResult:
        """Устанавливает модель Kandinsky через клиент и сохраняет в репозиторий.

        Клиент только выбирает модель, а сохранение выполняется в app-слое.

        Args:
            model_identifier: ID модели или часть названия для поиска.

        Returns:
            SetModelResult с информацией о результате установки.

        Raises:
            ValueError: Если клиент не настроен или модель не найдена.
            AuthenticationError: Если API ключи неверны.
            NetworkError: При сетевых ошибках.
            APIError: При других ошибках API.
        """
        if not self._image_client:
            raise ValueError("Image client not configured")

        # Клиент только выбирает модель, но не сохраняет
        result = await self._image_client.set_model(model_identifier)

        # Сохраняем в репозиторий в app-слое
        if result.success and result.model_id and result.model_name:
            await self._models_repo.set_kandinsky_model(result.model_id, result.model_name)
            self.logger.info(
                f"Kandinsky model saved to repository: {result.model_name} (ID: {result.model_id})",
                event="model_set_kandinsky",
                status="success",
                model_id=result.model_id,
                model_name=result.model_name,
            )
            # Обновляем сообщение для пользователя
            msg = f"Модель установлена: {result.model_name} (ID: {result.model_id})"
            return SetModelResult.ok(msg, model_id=result.model_id, model_name=result.model_name)

        return result

    async def set_gigachat_model(self, model_name: str) -> SetModelResult:
        """Устанавливает модель GigaChat через клиент и сохраняет в репозиторий.

        Клиент только выбирает модель, а сохранение выполняется в app-слое.

        Args:
            model_name: Название модели для установки.

        Returns:
            SetModelResult с информацией о результате установки.

        Raises:
            ValueError: Если клиент не настроен или модель не найдена.
            AuthenticationError: Если API ключи неверны.
            NetworkError: При сетевых ошибках.
            APIError: При других ошибках API.
        """
        if not self._text_client:
            raise ValueError("Text client not configured")

        # Клиент только выбирает модель, но не сохраняет
        result = await self._text_client.set_model(model_name)

        # Сохраняем в репозиторий в app-слое
        if result.success and result.model_name:
            await self._models_repo.set_gigachat_model(result.model_name)
            self.logger.info(
                f"GigaChat model saved to repository: {result.model_name}",
                event="model_set_gigachat",
                status="success",
                model_name=result.model_name,
            )
            # Обновляем сообщение для пользователя
            msg = f"✅ Модель GigaChat установлена: {result.model_name}"
            return SetModelResult.ok(msg, model_name=result.model_name)

        return result
