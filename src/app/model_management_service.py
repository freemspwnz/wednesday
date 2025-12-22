"""Application-сервис для управления моделями ML-клиентов.

Инкапсулирует логику выбора и сохранения текущих моделей,
делегируя HTTP-запросы клиентам, а сохранение - репозиторию.
"""

from __future__ import annotations

from infra.clients.models.status import SetModelResult
from shared.base.base_service import BaseService
from shared.base.exceptions import APIError
from shared.protocols import ILogger, IModelsRepo, ITextToImageClient, ITextToTextClient


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

        # Получаем статус API, который содержит список моделей
        # Это даёт нам доступ к сырым данным через check_api_status
        status_result = await self._image_client.check_api_status(save_models=False)
        available_models = status_result.models

        # Парсим список моделей (формат: "Name (ID: xxx)")
        pipelines: list[tuple[str, str]] = []  # (name, id)
        for model_str in available_models:
            # Парсим строку вида "Name (ID: xxx)"
            if "(ID: " in model_str:
                try:
                    name_part = model_str.split("(ID: ")[0].strip()
                    id_part = model_str.split("(ID: ")[1].rstrip(")").strip()
                    pipelines.append((name_part, id_part))
                except Exception:
                    # Если не удалось распарсить, пропускаем
                    continue

        if not pipelines:
            msg = "Не удалось получить список моделей Kandinsky"
            self.logger.error(msg)
            raise APIError(msg)

        # 1. Точное совпадение по ID
        for name, pipeline_id in pipelines:
            if pipeline_id == model_identifier:
                await self._models_repo.set_kandinsky_model(pipeline_id, name)
                msg = f"Модель установлена: {name} (ID: {pipeline_id})"
                self.logger.info(f"Kandinsky model set: {msg}")
                return SetModelResult.ok(msg)

        # 2. Частичное совпадение по названию (регистронезависимо)
        model_identifier_lower = model_identifier.lower()
        matches: list[tuple[str, str]] = []
        for name, pipeline_id in pipelines:
            if model_identifier_lower in name.lower():
                matches.append((name, pipeline_id))

        if len(matches) == 1:
            selected_name, selected_id = matches[0]
            await self._models_repo.set_kandinsky_model(selected_id, selected_name)
            msg = f"Модель установлена: {selected_name} (ID: {selected_id})"
            self.logger.info(f"Kandinsky model set: {msg}")
            return SetModelResult.ok(msg)

        if len(matches) > 1:
            models_list = [f"{name} (ID: {id_})" for name, id_ in matches]
            msg = "Найдено несколько моделей:\n" + "\n".join(models_list) + "\n\nУточните название или используйте ID"
            self.logger.warning(f"Multiple Kandinsky models matched: {matches}")
            raise ValueError(msg)

        msg = f"Модель '{model_identifier}' не найдена. Используйте /list_models для просмотра доступных моделей."
        self.logger.warning(f"Kandinsky model not found: {model_identifier}")
        raise ValueError(msg)

    async def set_gigachat_model(self, model_name: str) -> SetModelResult:
        """Устанавливает модель GigaChat через клиент и сохраняет в репозиторий.

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

        # Получаем список моделей через клиент (без сохранения)
        available_models = await self._text_client.get_available_models(save_models=False)

        # Проверяем, что модель есть в списке доступных
        if model_name in available_models:
            # Сохраняем модель в репозиторий
            await self._models_repo.set_gigachat_model(model_name)
            msg = f"✅ Модель GigaChat установлена: {model_name}"
            self.logger.info(f"GigaChat model set: {model_name}")
            return SetModelResult.ok(msg)
        else:
            msg = f"❌ Модель '{model_name}' не найдена в списке доступных"
            self.logger.warning(f"GigaChat model not found: {model_name}")
            raise ValueError(msg)
