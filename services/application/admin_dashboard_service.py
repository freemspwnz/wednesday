"""Application‑сервис для агрегации данных админского дашборда.

Инкапсулирует сбор и форматирование:
- статуса бота и инфраструктуры для команды /status;
- списков доступных моделей для команды /list_models.

Хендлеры остаются тонкими и занимаются только:
- проверкой прав;
- парсингом аргументов;
- вызовом методов этого сервиса и отправкой сообщений.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.application.admin_dashboard_builders import (
    ModelsListData,
    ModelsListMessageBuilder,
    StatusData,
    StatusMessageBuilder,
)
from services.base.base_service import BaseService
from services.clients.interfaces import ITextToImageClient, ITextToTextClient
from services.protocols import IChatsRepo, IMetrics, IModelsRepo, IUsageTracker

if TYPE_CHECKING:
    pass

if TYPE_CHECKING:  # pragma: no cover - используется только для типизации
    pass


# Магические числа, связанные с форматированием и усечением сообщений
MAX_ERROR_DETAILS_LENGTH = 500
PERCENT_MULTIPLIER = 100


class AdminDashboardService(BaseService):
    """Application‑сервис для построения админских сводок."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        usage: IUsageTracker | None,
        chats: IChatsRepo | None,
        metrics: IMetrics | None,
        image_client: ITextToImageClient,
        text_client: ITextToTextClient | None,
        models_store: IModelsRepo | None,
        status_builder: StatusMessageBuilder | None = None,
        models_list_builder: ModelsListMessageBuilder | None = None,
    ) -> None:
        super().__init__()
        self._usage = usage
        self._chats = chats
        self._metrics = metrics
        self._image_client = image_client
        self._text_client = text_client
        self._models_store = models_store
        self._status_builder = status_builder or StatusMessageBuilder()
        self._models_list_builder = models_list_builder or ModelsListMessageBuilder()

    @property
    def image_client(self) -> ITextToImageClient:
        """Возвращает клиент для генерации изображений.

        Предоставляет публичный доступ к клиенту для установки моделей
        и других операций, требующих прямого взаимодействия с клиентом.
        """
        return self._image_client

    @property
    def text_client(self) -> ITextToTextClient | None:
        """Возвращает клиент для генерации текста.

        Предоставляет публичный доступ к клиенту для установки моделей
        и других операций, требующих прямого взаимодействия с клиентом.
        """
        return self._text_client

    async def build_status_message(
        self,
        bot_name: str,
    ) -> str:
        """Строит текст расширенного статуса бота для команды /status."""

        scheduler_status = "✅ Настроен (Celery)"

        # Проверка статуса Kandinsky API
        api_status: str = "⏳ Проверка..."
        current_kandinsky: tuple[str | None, str | None] = (None, None)
        try:
            api_ok: bool
            api_models: list[str]
            api_ok, api_status, api_models, current_kandinsky = await self._image_client.check_api_status()
            if not api_ok:
                self.logger.warning(f"Проверка API Kandinsky не прошла: {api_status}")

            # При наличии ModelsStore можно сохранить список доступных моделей
            if self._models_store is not None and api_models:
                try:
                    await self._models_store.set_kandinsky_available_models(api_models)
                except Exception as store_error:  # pragma: no cover - побочный эффект не критичен
                    self.logger.warning(f"Не удалось сохранить список моделей Kandinsky: {store_error}")
        except Exception as e:
            api_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
            self.logger.error(f"Ошибка при проверке API Kandinsky: {e}", exc_info=True)

        # Проверка GigaChat API
        gigachat_status: str = "N/A"
        current_gigachat: str | None = None
        if self._text_client:
            try:
                gigachat_ok: bool
                gigachat_ok, gigachat_status = await self._text_client.check_api_status()
                if not gigachat_ok:
                    self.logger.warning(f"Проверка API GigaChat не прошла: {gigachat_status}")

                # Получаем доступные модели GigaChat и сохраняем их при наличии ModelsStore
                gigachat_models = await self._text_client.get_available_models()
                if self._models_store is not None and gigachat_models:
                    try:
                        await self._models_store.set_gigachat_available_models(gigachat_models)
                    except Exception as store_error:  # pragma: no cover
                        self.logger.warning(f"Не удалось сохранить список моделей GigaChat: {store_error}")

                if self._models_store is not None:
                    current_gigachat = await self._models_store.get_gigachat_model() or "GigaChat"
            except Exception as e:
                gigachat_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
                self.logger.error(f"Ошибка при проверке GigaChat API: {e}", exc_info=True)
        else:
            gigachat_status = "⚠️  Не настроен (GIGACHAT_AUTHORIZATION_KEY не указан)"

        # Информация по лимитам использования
        usage_info = "N/A"
        if self._usage:
            try:
                total, threshold, quota = await self._usage.get_limits_info()
                used_percent = int(total / quota * PERCENT_MULTIPLIER) if quota else 0
                usage_info = f"{total}/{quota} ({used_percent}%), порог: {threshold}"
            except Exception as e:  # pragma: no cover - защита от нештатных ошибок
                self.logger.warning(f"Не удалось получить информацию об использовании: {e}")

        # Информация об активных чатах
        chats_info: str | int = "N/A"
        if self._chats:
            try:
                chats_ids = await self._chats.list_chat_ids()
                chats_info = len(chats_ids)
            except Exception as e:  # pragma: no cover
                self.logger.warning(f"Не удалось получить список чатов: {e}")

        # Метрики производительности
        metrics_text = "Не настроены"
        if self._metrics:
            try:
                m_sum = await self._metrics.get_summary()
                total_requests = m_sum["generations_total"]
                successful = m_sum["generations_success"]
                success_rate = (successful / total_requests * PERCENT_MULTIPLIER) if total_requests > 0 else 0
                metrics_text = (
                    f"• Всего запросов на генерацию: {total_requests}\n"
                    f"• Успешных генераций: {successful}\n"
                    f"• Процент успеха: {success_rate:.1f}%\n"
                    f"• Среднее время генерации: {m_sum['average_generation_time']}\n"
                    f"• Срабатываний circuit breaker: {m_sum['circuit_breaker_trips']}"
                )
            except Exception as e:  # pragma: no cover
                self.logger.warning(f"Не удалось получить метрики производительности: {e}")

        # Форматирование информации о текущих моделях
        if current_kandinsky[0]:
            kandinsky_current_text = f"  ⭐ Текущая модель: {current_kandinsky[1] or current_kandinsky[0]}"
        else:
            kandinsky_current_text = "  ⚠️ Модель не выбрана"

        if current_gigachat:
            gigachat_current_text = f"  ⭐ Текущая модель: {current_gigachat}"
        else:
            gigachat_current_text = "  ⚠️ Модель не выбрана"

        # Формируем данные для билдера
        status_data = StatusData(
            bot_name=bot_name,
            next_run_line="",  # Может быть расширено позже для отображения следующего запуска
            api_status=api_status,
            kandinsky_current_text=kandinsky_current_text,
            gigachat_status=gigachat_status,
            gigachat_current_text=gigachat_current_text,
            scheduler_status=scheduler_status,
            usage_info=usage_info,
            chats_info=chats_info,
            metrics_text=metrics_text,
        )

        return self._status_builder.build(status_data)

    async def build_models_list_message(self) -> str:
        """Строит текст для команды /list_models."""

        kandinsky_models: list[str] = []
        current_kandinsky: tuple[str | None, str | None] = (None, None)
        gigachat_models: list[str] = []
        current_gigachat: str | None = None
        gigachat_configured = self._text_client is not None

        # Kandinsky
        try:
            api_ok, api_status, api_models, current_kandinsky = await self._image_client.check_api_status()
            if not api_ok:
                self.logger.warning(f"Проверка API Kandinsky при /list_models не прошла: {api_status}")

            if api_models:
                kandinsky_models = api_models
                if self._models_store is not None:
                    try:
                        await self._models_store.set_kandinsky_available_models(api_models)
                    except Exception as store_error:  # pragma: no cover
                        self.logger.warning(f"Не удалось сохранить список моделей Kandinsky: {store_error}")
        except Exception as e:
            self.logger.error(f"Ошибка при получении моделей Kandinsky: {e}")
            if self._models_store is not None:
                try:
                    current_kandinsky = await self._models_store.get_kandinsky_model()
                except Exception:  # pragma: no cover
                    current_kandinsky = (None, None)

        # GigaChat
        if self._text_client:
            try:
                gigachat_models = await self._text_client.get_available_models()
                if self._models_store is not None:
                    try:
                        await self._models_store.set_gigachat_available_models(gigachat_models)
                        current_gigachat = await self._models_store.get_gigachat_model()
                    except Exception as store_error:  # pragma: no cover
                        self.logger.warning(f"Не удалось сохранить или получить модели GigaChat: {store_error}")
            except Exception as e:
                self.logger.error(f"Ошибка при получении моделей GigaChat: {e}")
                if self._models_store is not None:
                    try:
                        current_gigachat = await self._models_store.get_gigachat_model()
                    except Exception:  # pragma: no cover
                        current_gigachat = None

        # Формируем данные для билдера
        models_list_data = ModelsListData(
            kandinsky_models=kandinsky_models,
            kandinsky_current=current_kandinsky,
            gigachat_models=gigachat_models,
            gigachat_current=current_gigachat,
            gigachat_configured=gigachat_configured,
        )

        return self._models_list_builder.build(models_list_data)
