"""Application‑сервис для агрегации данных админского дашборда.

Инкапсулирует сбор данных:
- статуса бота и инфраструктуры для команды /status;
- списков доступных моделей для команды /list_models.

Форматирование данных выполняется в билдерах (StatusMessageBuilder, ModelsListMessageBuilder).

Хендлеры остаются тонкими и занимаются только:
- проверкой прав;
- парсингом аргументов;
- вызовом методов этого сервиса и отправкой сообщений.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.admin_dashboard_builders import (
    ModelsListData,
    ModelsListMessageBuilder,
    StatusData,
    StatusMessageBuilder,
)
from app.api_status_service import APIStatusService
from shared.base.base_service import BaseService
from shared.base.exceptions import RepoError, ServiceError
from shared.protocols import IChatsRepo, ILogger, IMetrics, IUsageTracker

if TYPE_CHECKING:
    pass


class AdminDashboardService(BaseService):
    """Application‑сервис для построения админских сводок.

    Отвечает только за сбор данных из различных источников (repositories, services).
    Форматирование данных в текстовые сообщения выполняется в билдерах.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        usage: IUsageTracker | None,
        chats: IChatsRepo | None,
        metrics: IMetrics | None,
        api_status_service: APIStatusService,
        status_builder: StatusMessageBuilder | None = None,
        models_list_builder: ModelsListMessageBuilder | None = None,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис админского дашборда.

        Args:
            usage: Трекер использования (опционально).
            chats: Репозиторий чатов (опционально).
            metrics: Сервис метрик (опционально).
            api_status_service: Сервис проверки статуса API (обязателен).
            status_builder: Билдер сообщений статуса (опционально).
            models_list_builder: Билдер сообщений списка моделей (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._usage = usage
        self._chats = chats
        self._metrics = metrics
        self._api_status_service = api_status_service
        self._status_builder = status_builder or StatusMessageBuilder()
        self._models_list_builder = models_list_builder or ModelsListMessageBuilder()

    async def build_status_message(
        self,
        bot_name: str,
    ) -> str:
        """Строит текст расширенного статуса бота для команды /status."""

        scheduler_status = "✅ Настроен (Celery)"

        # Проверка статуса Kandinsky API
        kandinsky_status = await self._api_status_service.check_image_api_status()
        api_status = kandinsky_status.status_message
        current_kandinsky = (kandinsky_status.current_model_id, kandinsky_status.current_model_name)

        # Проверка GigaChat API
        gigachat_status_obj = await self._api_status_service.check_text_api_status()
        gigachat_status = gigachat_status_obj.status_message
        current_gigachat = gigachat_status_obj.current_model

        # Собираем сырые данные для usage_info
        usage_total = None
        usage_threshold = None
        usage_quota = None
        if self._usage:
            try:
                usage_total, usage_threshold, usage_quota = await self._usage.get_limits_info()
            except (RepoError, ServiceError) as e:  # pragma: no cover - защита от нештатных ошибок
                self.logger.warning(
                    f"Не удалось получить информацию об использовании: {e}",
                    event="repo_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        # Собираем сырые данные для chats_info
        chats_count = None
        if self._chats:
            try:
                chats_ids = await self._chats.list_chat_ids()
                chats_count = len(chats_ids) if chats_ids else 0
            except RepoError as e:  # pragma: no cover
                self.logger.warning(
                    f"Не удалось получить список чатов: {e}",
                    event="repo_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        # Собираем сырые данные для metrics_text
        metrics_summary = None
        if self._metrics:
            try:
                metrics_summary = await self._metrics.get_summary()
            except ServiceError as e:  # pragma: no cover
                self.logger.warning(
                    f"Не удалось получить метрики производительности: {e}",
                    event="service_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        # Формируем данные для билдера
        status_data = StatusData(
            bot_name=bot_name,
            next_run_line="",  # Может быть расширено позже для отображения следующего запуска
            api_status=api_status,
            kandinsky_current_id=current_kandinsky[0],
            kandinsky_current_name=current_kandinsky[1],
            gigachat_status=gigachat_status,
            gigachat_current=current_gigachat,
            scheduler_status=scheduler_status,
            usage_total=usage_total,
            usage_threshold=usage_threshold,
            usage_quota=usage_quota,
            chats_count=chats_count,
            metrics_summary=metrics_summary,
        )

        return self._status_builder.build(status_data)

    async def build_models_list_message(self) -> str:
        """Строит текст для команды /list_models."""

        # Получаем статусы API
        kandinsky_status = await self._api_status_service.check_image_api_status()
        gigachat_status_obj = await self._api_status_service.check_text_api_status()

        kandinsky_models = kandinsky_status.available_models
        current_kandinsky = (kandinsky_status.current_model_id, kandinsky_status.current_model_name)
        gigachat_models = gigachat_status_obj.available_models
        current_gigachat = gigachat_status_obj.current_model
        gigachat_configured = (
            gigachat_status_obj.status_message != "⚠️ Не настроен (GIGACHAT_AUTHORIZATION_KEY не указан)"
        )

        # Формируем данные для билдера
        models_list_data = ModelsListData(
            kandinsky_models=kandinsky_models,
            kandinsky_current=current_kandinsky,
            gigachat_models=gigachat_models,
            gigachat_current=current_gigachat,
            gigachat_configured=gigachat_configured,
        )

        return self._models_list_builder.build(models_list_data)
