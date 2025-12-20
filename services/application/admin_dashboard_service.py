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

from services.application.admin_dashboard_builders import (
    ModelsListData,
    ModelsListMessageBuilder,
    StatusData,
    StatusMessageBuilder,
)
from services.base.base_service import BaseService
from services.clients.exceptions import APIError, AuthenticationError, NetworkError
from services.protocols import IChatsRepo, IMetrics, IModelsRepo, ITextToImageClient, ITextToTextClient, IUsageTracker

if TYPE_CHECKING:
    pass

if TYPE_CHECKING:  # pragma: no cover - используется только для типизации
    pass


# Магические числа, связанные с форматированием и усечением сообщений
MAX_ERROR_DETAILS_LENGTH = 500


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
            result = await self._image_client.check_api_status()
            api_status = result.message
            api_models = result.models
            current_kandinsky = (result.current_model_id, result.current_model_name)

            # При наличии ModelsStore можно сохранить список доступных моделей
            if self._models_store is not None and api_models:
                try:
                    await self._models_store.set_kandinsky_available_models(api_models)
                except Exception as store_error:  # pragma: no cover - побочный эффект не критичен
                    self.logger.warning(f"Не удалось сохранить список моделей Kandinsky: {store_error}")
        except (AuthenticationError, NetworkError, APIError) as e:
            api_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
            self.logger.error(f"Ошибка при проверке API Kandinsky: {e}", exc_info=True)
        except Exception as e:  # pragma: no cover - защита от неожиданных ошибок
            api_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
            self.logger.error(f"Неожиданная ошибка при проверке API Kandinsky: {e}", exc_info=True)

        # Проверка GigaChat API
        gigachat_status: str = "N/A"
        current_gigachat: str | None = None
        if self._text_client:
            try:
                result = await self._text_client.check_api_status()
                gigachat_status = result.message
                current_gigachat = result.current_model_name

                # Получаем доступные модели GigaChat и сохраняем их при наличии ModelsStore
                try:
                    gigachat_models = await self._text_client.get_available_models()
                    if self._models_store is not None and gigachat_models:
                        try:
                            await self._models_store.set_gigachat_available_models(gigachat_models)
                        except Exception as store_error:  # pragma: no cover
                            self.logger.warning(f"Не удалось сохранить список моделей GigaChat: {store_error}")
                except (AuthenticationError, NetworkError, APIError) as e:
                    self.logger.warning(f"Не удалось получить список моделей GigaChat: {e}")

                if self._models_store is not None and not current_gigachat:
                    current_gigachat = await self._models_store.get_gigachat_model() or "GigaChat"
            except (AuthenticationError, NetworkError, APIError) as e:
                gigachat_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
                self.logger.error(f"Ошибка при проверке GigaChat API: {e}", exc_info=True)
            except Exception as e:  # pragma: no cover - защита от неожиданных ошибок
                gigachat_status = f"❌ Ошибка: {str(e)[: MAX_ERROR_DETAILS_LENGTH // 10]}"
                self.logger.error(f"Неожиданная ошибка при проверке GigaChat API: {e}", exc_info=True)
        else:
            gigachat_status = "⚠️  Не настроен (GIGACHAT_AUTHORIZATION_KEY не указан)"

        # Собираем сырые данные для usage_info
        usage_total = None
        usage_threshold = None
        usage_quota = None
        if self._usage:
            try:
                usage_total, usage_threshold, usage_quota = await self._usage.get_limits_info()
            except Exception as e:  # pragma: no cover - защита от нештатных ошибок
                self.logger.warning(f"Не удалось получить информацию об использовании: {e}")

        # Собираем сырые данные для chats_info
        chats_count = None
        if self._chats:
            try:
                chats_ids = await self._chats.list_chat_ids()
                chats_count = len(chats_ids) if chats_ids else 0
            except Exception as e:  # pragma: no cover
                self.logger.warning(f"Не удалось получить список чатов: {e}")

        # Собираем сырые данные для metrics_text
        metrics_summary = None
        if self._metrics:
            try:
                metrics_summary = await self._metrics.get_summary()
            except Exception as e:  # pragma: no cover
                self.logger.warning(f"Не удалось получить метрики производительности: {e}")

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

        kandinsky_models: list[str] = []
        current_kandinsky: tuple[str | None, str | None] = (None, None)
        gigachat_models: list[str] = []
        current_gigachat: str | None = None
        gigachat_configured = self._text_client is not None

        # Kandinsky
        try:
            result = await self._image_client.check_api_status()
            if result.models:
                kandinsky_models = result.models
                current_kandinsky = (result.current_model_id, result.current_model_name)
                if self._models_store is not None:
                    try:
                        await self._models_store.set_kandinsky_available_models(result.models)
                    except Exception as store_error:  # pragma: no cover
                        self.logger.warning(f"Не удалось сохранить список моделей Kandinsky: {store_error}")
        except (AuthenticationError, NetworkError, APIError) as e:
            self.logger.error(f"Ошибка при получении моделей Kandinsky: {e}")
            if self._models_store is not None:
                try:
                    current_kandinsky = await self._models_store.get_kandinsky_model()
                except Exception:  # pragma: no cover
                    current_kandinsky = (None, None)
        except Exception as e:  # pragma: no cover - защита от неожиданных ошибок
            self.logger.error(f"Неожиданная ошибка при получении моделей Kandinsky: {e}")
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
            except (AuthenticationError, NetworkError, APIError) as e:
                self.logger.error(f"Ошибка при получении моделей GigaChat: {e}")
                if self._models_store is not None:
                    try:
                        current_gigachat = await self._models_store.get_gigachat_model()
                    except Exception:  # pragma: no cover
                        current_gigachat = None
            except Exception as e:  # pragma: no cover - защита от неожиданных ошибок
                self.logger.error(f"Неожиданная ошибка при получении моделей GigaChat: {e}")
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
