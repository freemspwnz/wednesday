"""
Клиент для работы с API Kandinsky (Fusion Brain).

Этот модуль инкапсулирует всю сетевую/HTTP‑логику:

- формирование заголовков авторизации;
- запросы к эндпоинтам `pipelines`, `pipeline/run`, `pipeline/status`;
- парсинг ответов и базовую валидацию;
- обработку сетевых ошибок и таймаутов;
- простую retry‑политику на уровне HTTP.

Бизнес‑логика генерации жабы (кеш, метрики, circuit breaker, выбор подписи
и промпта, работа с БД) остаётся в `services.image_generator.ImageGenerator`.
Он использует этот клиент через абстракцию `ITextToImageClient`.

Используем Loguru для структурированного логирования:

- базовый логгер конфигурируется в `utils.logger`;
- для сетевых событий создаём "обогащённый" логгер через
  `logger.bind(event="...", user_id=user_id)` и пишем краткие текстовые
  сообщения без бинарных данных;
- JSON‑sink Loguru автоматически добавляет все bound‑поля в структуру лога,
  что упрощает анализ запросов и ошибок по полям `event`, `user_id`,
  `status`, `attempt` и т.п.
"""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from types import TracebackType
from typing import Any, Final, Self

import aiohttp
from loguru import logger
from PIL import Image

from infra.clients.base import BaseHTTPClient
from infra.clients.models import (
    KandinskyGenerationParams,
    KandinskyGenerationRequest,
    KandinskyGenerationStartResponse,
    KandinskyPipelineResponse,
    KandinskyStatus,
    KandinskyStatusResponse,
)
from infra.clients.sber_clients_exceptions import map_client_errors
from shared.base.exceptions import APIError, NetworkError
from shared.config import KandinskyConfig
from shared.models import APIStatusResult, SetModelResult
from shared.protocols import IModelsRepo, ITextToImageClient

HTTP_STATUS_OK: Final[int] = 200
HTTP_STATUS_UNAUTHORIZED: Final[int] = 401
HTTP_STATUS_FORBIDDEN: Final[int] = 403

MAX_STATUS_ATTEMPTS: Final[int] = 10
STATUS_POLL_DELAY_SECONDS: Final[int] = 10


class KandinskyClient(BaseHTTPClient, ITextToImageClient):
    """HTTP‑клиент Kandinsky, реализующий интерфейс `ITextToImageClient`.

    Архитектурно клиент отвечает только за:

    - корректное обращение к HTTP‑эндпоинтам Kandinsky;
    - авторизацию и выбор модели (pipeline);
    - обработку сетевых ошибок и таймаутов;
    - преобразование ответа API в байты изображения.

    Любые бизнес‑аспекты (кеш, Prometheus, record_metric, circuit breaker,
    выбор подписи и т.п.) реализуются на уровне сервисов, использующих
    этот клиент.
    """

    # Константы эндпоинтов
    ENDPOINT_PIPELINES = "key/api/v1/pipelines"
    ENDPOINT_PIPELINE_RUN = "key/api/v1/pipeline/run"
    ENDPOINT_PIPELINE_STATUS = "key/api/v1/pipeline/status"

    def __init__(self, config: KandinskyConfig, models_repo: IModelsRepo) -> None:
        """Инициализация клиента Kandinsky.

        Args:
            config: Конфигурация Kandinsky клиента (обязательна).
            models_repo: Репозиторий моделей для сохранения/получения настроек моделей.
        """
        self._api_key: str | None = config.api_key
        self._secret_key: str | None = config.secret_key
        self._base_url: str = config.base_url
        self._proxy_url: str | None = None
        self._models_repo: IModelsRepo = models_repo
        self._config: KandinskyConfig = config

        # Proxy берём из стандартных переменных окружения, как и в старой реализации.
        import os

        self._proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

        # Настройка timeout для сессии (используем таймауты генерации как основные)
        self._timeout = config.generation_timeout.to_client_timeout()

        # Создаём connector (один раз для переиспользования)
        connector: aiohttp.BaseConnector | None = None
        if self._proxy_url:
            # ProxyConnector не типизирован стабильно в aiohttp, поэтому игнорируем attr‑check.
            connector = aiohttp.ProxyConnector.from_url(self._proxy_url)  # type: ignore[attr-defined]

        # Создаём сессию для переиспользования во всех методах
        self._session = aiohttp.ClientSession(timeout=self._timeout, connector=connector)

        # Инициализируем базовый класс
        super().__init__(
            base_url=config.base_url,
            session=self._session,
            service_name="kandinsky",
            default_timeout=config.generation_timeout.to_client_timeout(),
        )

    # ------------------------------------------------------------------ #
    # Публичный интерфейс ITextToImageClient                             #
    # ------------------------------------------------------------------ #

    @map_client_errors(event_name="kandinsky_generate", service_name="kandinsky")
    async def generate(self, prompt: str, user_id: str | None = None) -> bytes:  # type: ignore[override]
        """Генерирует изображение по текстовому промпту через Kandinsky API.

        Выполняет полный цикл генерации: получение pipeline ID, запуск генерации,
        ожидание завершения и получение результата.

        Args:
            prompt: Текстовое описание изображения для генерации.
            user_id: Идентификатор пользователя для логирования (опционально).

        Returns:
            Байты изображения в формате PNG.

        Raises:
            ValueError: Если API ключи не сконфигурированы.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="kandinsky_generate", user_id=user_id)
        bound.info("Запрос генерации изображения через Kandinsky API получен")

        try:
            headers = self._get_auth_headers()
        except ValueError as exc:
            bound.error("API ключи Kandinsky не сконфигурированы: {}", str(exc))
            raise

        if self._proxy_url:
            bound.bind(proxy_url=self._proxy_url).info("Используется прокси для запроса к Kandinsky")

        # Используем переиспользуемую сессию
        pipeline_id = await self._get_pipeline_id(headers, user_id=user_id)

        uuid = await self._start_generation(headers, pipeline_id, prompt, user_id=user_id)

        image_data = await self._wait_for_generation(headers, uuid, user_id=user_id)

        # В логах не показываем бинарные данные, только размеры.
        bound.bind(image_size_bytes=len(image_data)).info(
            "Изображение успешно получено от Kandinsky",
        )
        return image_data

    # ------------------------------------------------------------------ #
    # Дополнительные методы для healthcheck и админ‑команд               #
    # ------------------------------------------------------------------ #

    async def check_api_status(
        self,
        save_models: bool = True,
    ) -> APIStatusResult:
        """Проверяет статус API и валидность ключа без генерации изображения (dry-run).

        Выполняет проверку доступности API и валидности ключей через запрос
        списка доступных pipelines (моделей).

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            APIStatusResult с информацией о статусе API и списком моделей.

        Raises:
            ValueError: Если API ключи не сконфигурированы.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="kandinsky_status_check")
        bound.debug("Начало проверки статуса Kandinsky (save_models={})", save_models)

        try:
            headers = self._get_auth_headers()
        except ValueError as exc:
            bound.bind(error=str(exc)).error("Ошибка конфигурации ключей")
            raise

        # Используем меньший таймаут для проверки статуса
        timeout = self._config.check_timeout.to_client_timeout()

        current_pipeline_id, current_pipeline_name = await self._models_repo.get_kandinsky_model()

        bound.debug("Запрос списка pipelines для dry‑run статуса")
        pipelines_data_json = await self._fetch_pipelines(headers=headers, timeout=timeout)
        if isinstance(pipelines_data_json, list) and pipelines_data_json:
            pipelines = [KandinskyPipelineResponse.model_validate(p) for p in pipelines_data_json]

            if save_models:
                await self._models_repo.set_kandinsky_available_models(pipelines_data_json)
                bound.debug(
                    "Сохранён список из {} моделей Kandinsky",
                    len(pipelines),
                )

            models_list: list[str] = []
            for pipeline in pipelines:
                model_name = pipeline.name
                model_id = pipeline.id
                is_current = " ⭐" if (current_pipeline_id and model_id == current_pipeline_id) else ""
                models_list.append(f"{model_name} (ID: {model_id}){is_current}")

            return APIStatusResult.success(
                message="✅ API доступен, ключ валиден",
                models=models_list,
                current_model_id=current_pipeline_id,
                current_model_name=current_pipeline_name,
            )
        else:
            return APIStatusResult.success(
                message="✅ API доступен, ключ валиден (модели не найдены)",
                models=["Модели не найдены"],
                current_model_id=current_pipeline_id,
                current_model_name=current_pipeline_name,
            )

    @map_client_errors(event_name="kandinsky_get_models", service_name="kandinsky")
    async def get_available_models(self, save_models: bool = True) -> list[str]:  # type: ignore[override]
        """Возвращает список доступных моделей Kandinsky.

        Получает список доступных pipelines (моделей) через API или из хранилища.
        Сначала пытается получить модели через check_api_status, затем из хранилища.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей
                в хранилище для последующего использования.

        Returns:
            Список доступных моделей в формате "Name (ID: xxx)".

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="kandinsky_get_available_models", save_models=save_models)
        bound.debug("Запрос списка доступных моделей Kandinsky")

        # Пытаемся получить через check_api_status, который уже возвращает список моделей
        try:
            result = await self.check_api_status(save_models=save_models)
            if result.models:
                bound.debug("Получен список из {} моделей через check_api_status", len(result.models))
                return result.models
            # Если список пустой, пробрасываем исключение
            bound.warning("check_api_status вернул пустой список моделей")
            raise APIError(
                "Не удалось получить список моделей Kandinsky: API вернул пустой список",
            )
        except Exception as exc:
            # Fallback: пытаемся получить из хранилища
            bound.debug("Попытка получить модели из хранилища после ошибки API")
            try:
                stored_models = await self._models_repo.get_kandinsky_available_models()
                if stored_models:
                    bound.debug("Получен список из {} моделей из хранилища", len(stored_models))
                    return stored_models
            except Exception as store_exc:
                bound.warning("Не удалось получить модели из хранилища: {}", str(store_exc))

            # Если ничего не получилось, пробрасываем исходное исключение
            bound.error("Не удалось получить список моделей ни через API, ни из хранилища")
            raise APIError(
                f"Не удалось получить список моделей Kandinsky: {exc}",
                original_error=exc,
            ) from exc

    @map_client_errors(event_name="kandinsky_set_model", service_name="kandinsky")
    async def set_model(self, model_identifier: str) -> SetModelResult:  # type: ignore[override]
        """Выбирает модель (pipeline) по ID или части названия.

        Выполняет поиск модели по точному совпадению ID или частичному совпадению
        названия (регистронезависимо). НЕ сохраняет модель в хранилище - это
        ответственность app-слоя. Возвращает информацию о выбранной модели.

        Args:
            model_identifier: ID модели или часть названия для поиска.

        Returns:
            SetModelResult с информацией о выбранной модели (model_id, model_name).

        Raises:
            ValueError: Если API ключи не сконфигурированы или модель не найдена.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="kandinsky_set_model", model_identifier=model_identifier)

        try:
            headers = self._get_auth_headers()
        except ValueError as exc:
            bound.bind(error=str(exc)).error("Ошибка конфигурации ключей")
            raise

        # Используем меньший таймаут для установки модели
        timeout = self._config.check_timeout.to_client_timeout()
        pipelines_data_json = await self._fetch_pipelines(headers=headers, timeout=timeout)
        if not isinstance(pipelines_data_json, list):
            bound.error("Ответ Kandinsky API не является списком моделей")
            raise APIError(
                "Не удалось получить список моделей от Kandinsky API",
            )

        pipelines = [KandinskyPipelineResponse.model_validate(p) for p in pipelines_data_json]

        # 1. Точное совпадение по ID.
        for pipeline in pipelines:
            if pipeline.id == model_identifier:
                matched_model_name = pipeline.name
                matched_pipeline_id = pipeline.id
                msg = f"Модель выбрана: {matched_model_name} (ID: {matched_pipeline_id})"
                bound.info(msg)
                return SetModelResult.ok(
                    msg,
                    model_id=matched_pipeline_id,
                    model_name=matched_model_name,
                )

        # 2. Частичное совпадение по названию (регистронезависимо).
        model_identifier_lower = model_identifier.lower()
        matches: list[KandinskyPipelineResponse] = []
        for pipeline in pipelines:
            if model_identifier_lower in pipeline.name.lower():
                matches.append(pipeline)

        if len(matches) == 1:
            matched_pipeline = matches[0]
            selected_model_name = matched_pipeline.name
            selected_pipeline_id = matched_pipeline.id
            msg = f"Модель выбрана: {selected_model_name} (ID: {selected_pipeline_id})"
            bound.info(msg)
            return SetModelResult.ok(
                msg,
                model_id=selected_pipeline_id,
                model_name=selected_model_name,
            )

        if len(matches) > 1:
            models_list = [f"{p.name} (ID: {p.id})" for p in matches]
            msg = "Найдено несколько моделей:\n" + "\n".join(models_list) + "\n\nУточните название или используйте ID"
            bound.warning("Несколько моделей соответствуют запросу: {}", models_list)
            raise ValueError(msg)

        msg = f"Модель '{model_identifier}' не найдена. Используйте /status для просмотра доступных моделей."
        bound.warning(msg)
        raise ValueError(msg)

    # ------------------------------------------------------------------ #
    # Внутренние helpers                                                 #
    # ------------------------------------------------------------------ #
    #
    # ШАБЛОНЫ ДЛЯ ДОБАВЛЕНИЯ НОВЫХ МЕТОДОВ:
    #
    # 1. Простой GET запрос с JSON:
    #    async def method_name(self, param: str) -> dict[str, Any]:
    #        return await self._get_json(
    #            endpoint=f"key/api/v1/endpoint/{param}",
    #            method_name="method_name",
    #            headers=self._get_auth_headers(),
    #        )
    #
    # 2. GET с кастомной обработкой (Pydantic валидация):
    #    async def method_name(self, param: str) -> ModelType:
    #        response = await self._get(
    #            endpoint=f"key/api/v1/endpoint/{param}",
    #            method_name="method_name",
    #            headers=self._get_auth_headers(),
    #        )
    #        async with response:
    #            data = await self._parse_json_response(response)
    #            return ModelType.model_validate(data)
    #
    # 3. POST с JSON:
    #    async def method_name(self, data: dict[str, Any]) -> dict[str, Any]:
    #        return await self._post_json(
    #            endpoint="key/api/v1/endpoint",
    #            method_name="method_name",
    #            headers=self._get_auth_headers(),
    #            json=data,
    #        )
    #
    # 4. POST с FormData:
    #    async def method_name(self, file_data: bytes) -> dict[str, Any]:
    #        form_data = aiohttp.FormData()
    #        form_data.add_field("file", file_data, filename="file.png")
    #        response = await self._post(
    #            endpoint="key/api/v1/upload",
    #            method_name="method_name",
    #            headers=self._get_auth_headers(),
    #            data=form_data,
    #        )
    #        async with response:
    #            return await self._parse_json_response(response)
    #

    def _get_auth_headers(self) -> dict[str, str]:
        """Формирует заголовки авторизации и валидирует ключи."""
        api_key = self._api_key or ""
        secret_key = self._secret_key or ""
        if not api_key or not secret_key:
            raise ValueError("API ключи Kandinsky не установлены")
        return {
            "X-Key": f"Key {api_key}",
            "X-Secret": f"Secret {secret_key}",
        }

    async def _fetch_pipelines(
        self,
        headers: dict[str, str],
        timeout: aiohttp.ClientTimeout | None = None,
    ) -> list[dict[str, Any]]:
        """Получает список pipelines (моделей) Kandinsky.

        Args:
            headers: Заголовки авторизации.
            timeout: Таймаут для запроса (опционально).

        Returns:
            Список pipelines в виде словарей.

        Raises:
            AuthenticationError: При ошибках аутентификации (401, 403).
            RateLimitError: При превышении лимита запросов (429).
            NetworkError: При сетевых ошибках.
            APIError: При других ошибках API.
        """
        pipelines_data = await self._get_json(
            endpoint=self.ENDPOINT_PIPELINES,
            method_name="get_pipelines",
            headers=headers,
            timeout=timeout,
        )
        if not isinstance(pipelines_data, list):
            raise APIError(
                "Ответ Kandinsky API не является списком pipelines",
            )
        return pipelines_data

    async def _get_pipeline_id(
        self,
        headers: dict[str, str],
        *,
        user_id: str | None = None,
    ) -> str:
        """Выбирает актуальный pipeline ID, используя сохранённую модель или первую доступную."""
        bound = logger.bind(event="kandinsky_get_pipeline", user_id=user_id)
        saved_pipeline_id, saved_pipeline_name = await self._models_repo.get_kandinsky_model()

        data_json = await self._fetch_pipelines(headers=headers)
        if not data_json or not isinstance(data_json, list):
            bound.error("Пустой ответ при получении pipelines от Kandinsky")
            raise APIError(
                "Пустой ответ при получении pipelines от Kandinsky",
            )

        pipelines = [KandinskyPipelineResponse.model_validate(p) for p in data_json]

        if saved_pipeline_id:
            for pipeline in pipelines:
                if pipeline.id == saved_pipeline_id:
                    bound.bind(
                        pipeline_id=saved_pipeline_id,
                        pipeline_name=saved_pipeline_name,
                    ).info("Используется сохранённая модель Kandinsky")
                    return saved_pipeline_id

            bound.warning(
                "Сохранённая модель {} не найдена среди доступных; используется первая доступная.",
                saved_pipeline_id,
            )

        if not pipelines:
            bound.error("Список pipelines пуст")
            raise APIError(
                "Список pipelines Kandinsky пуст",
            )

        first_pipeline = pipelines[0]
        pipeline_id: str = str(first_pipeline.id)
        pipeline_name: str = str(first_pipeline.name)
        # НЕ сохраняем модель здесь - это ответственность app-слоя
        # Метод используется только для получения pipeline_id при генерации
        bound.bind(pipeline_id=pipeline_id, pipeline_name=pipeline_name).info(
            "Выбран pipeline для генерации через Kandinsky",
        )
        return pipeline_id

    async def _start_generation(
        self,
        headers: dict[str, str],
        pipeline_id: str,
        prompt: str,
        *,
        user_id: str | None = None,
    ) -> str:
        """Создаёт задачу генерации и возвращает UUID."""
        bound = logger.bind(event="kandinsky_start_generation", user_id=user_id, pipeline_id=pipeline_id)

        params = KandinskyGenerationRequest(
            type="GENERATE",
            numImages=1,
            width=1024,
            height=1024,
            generateParams=KandinskyGenerationParams(query=prompt),
        )

        form_data = aiohttp.FormData()
        form_data.add_field("pipeline_id", pipeline_id)
        # Параметры передаём как JSON‑строку, как того требует API Fusion Brain.
        form_data.add_field(
            "params", params.model_dump_json(by_alias=True, exclude_none=True), content_type="application/json"
        )

        response = await self._post(
            endpoint=self.ENDPOINT_PIPELINE_RUN,
            method_name="start_generation",
            headers=headers,
            data=form_data,
        )

        async with response:
            # Принимаем как 200, так и 201 как успешные статусы
            if response.status in {200, 201}:
                result_json = await self._parse_json_response(response, expected_status=response.status)
                result = KandinskyGenerationStartResponse.model_validate(result_json)
                uuid_str: str = str(result.uuid)
                bound.bind(task_uuid=uuid_str).info("Задача генерации на Kandinsky успешно создана")
                return uuid_str
            else:
                # Если статус не 200/201, _parse_json_response выбросит исключение
                await self._parse_json_response(response, expected_status=200)
                # Этот код не должен выполняться, но нужен для mypy
                raise APIError(
                    "Неожиданный статус ответа при запуске генерации",
                )

    async def _wait_for_generation(
        self,
        headers: dict[str, str],
        uuid: str,
        *,
        user_id: str | None = None,
    ) -> bytes:
        """Ожидает завершения задачи генерации и возвращает байты изображения."""
        bound = logger.bind(event="kandinsky_poll_generation", user_id=user_id, task_uuid=uuid)

        last_exception: Exception | None = None
        for attempt in range(1, MAX_STATUS_ATTEMPTS + 1):
            try:
                endpoint = f"{self.ENDPOINT_PIPELINE_STATUS}/{uuid}"
                response = await self._get(
                    endpoint=endpoint,
                    method_name="wait_for_generation_status",
                    headers=headers,
                )

                async with response:
                    data_json = await self._parse_json_response(response)
                    status_response = KandinskyStatusResponse.model_validate(data_json)

                    status = status_response.status

                    if status == KandinskyStatus.DONE:
                        if not status_response.result:
                            bound.error("Ответ Kandinsky со статусом DONE без результата")
                            raise APIError(
                                "Ответ Kandinsky со статусом DONE без результата",
                            )

                        files = status_response.result.files
                        if not files:
                            bound.error("Ответ Kandinsky со статусом DONE без файлов результата")
                            raise APIError(
                                "Ответ Kandinsky со статусом DONE без файлов результата",
                            )

                        image_base64 = files[0]
                        try:
                            image_data = base64.b64decode(image_base64)
                        except Exception as exc:  # pragma: no cover - практически не воспроизводится
                            bound.bind(error=str(exc)).error(
                                "Не удалось декодировать base64‑изображение от Kandinsky",
                            )
                            raise APIError(
                                f"Не удалось декодировать base64‑изображение от Kandinsky: {exc}",
                                original_error=exc,
                            ) from exc

                        # Валидация, что это действительно изображение.
                        try:
                            Image.open(BytesIO(image_data))
                        except Exception as exc:
                            bound.bind(error=str(exc)).error(
                                "Полученные данные от Kandinsky не являются валидным изображением",
                            )
                            raise APIError(
                                f"Полученные данные от Kandinsky не являются валидным изображением: {exc}",
                                original_error=exc,
                            ) from exc

                        bound.bind(attempt=attempt).info(
                            "Генерация изображения на Kandinsky завершена успешно",
                        )
                        return image_data

                    if status == KandinskyStatus.FAIL:
                        error_desc = status_response.errorDescription or "Неизвестная ошибка"
                        bound.bind(error_description=error_desc, attempt=attempt).error(
                            "Генерация на Kandinsky завершилась с ошибкой",
                        )
                        raise APIError(
                            f"Генерация на Kandinsky завершилась с ошибкой: {error_desc}",
                        )

                    if status in {KandinskyStatus.INITIAL, KandinskyStatus.PROCESSING}:
                        bound.bind(status=str(status), attempt=attempt).info(
                            "Генерация на Kandinsky ещё выполняется, продолжаем ожидание",
                        )
                        await asyncio.sleep(STATUS_POLL_DELAY_SECONDS)
                        continue

                    bound.bind(raw_status=str(status), attempt=attempt).error(
                        "Kandinsky вернул неизвестный статус генерации",
                    )
                    raise APIError(
                        f"Kandinsky вернул неизвестный статус генерации: {status}",
                    )

            except aiohttp.ClientConnectorError as exc:
                last_exception = exc
                bound.bind(attempt=attempt, error=str(exc)).error(
                    "Ошибка подключения при проверке статуса генерации Kandinsky",
                )
            except aiohttp.ClientError as exc:
                last_exception = exc
                bound.bind(attempt=attempt, error=str(exc)).error(
                    "Ошибка клиента при проверке статуса генерации Kandinsky",
                )
            except TimeoutError as exc:
                last_exception = exc
                bound.bind(attempt=attempt).warning(
                    "Таймаут при проверке статуса генерации Kandinsky",
                )
            except Exception as exc:  # pragma: no cover - защитный фоллбек
                last_exception = exc
                bound.bind(attempt=attempt, error=str(exc)).error(
                    "Неожиданная ошибка при проверке статуса генерации Kandinsky",
                )

            if attempt < MAX_STATUS_ATTEMPTS:
                await asyncio.sleep(STATUS_POLL_DELAY_SECONDS)

        bound.error(
            "Превышено максимальное количество попыток проверки статуса генерации Kandinsky ({} попыток)",
            MAX_STATUS_ATTEMPTS,
        )
        if last_exception:
            if isinstance(
                last_exception,
                aiohttp.ClientConnectorError | aiohttp.ClientError | TimeoutError,
            ):
                raise NetworkError(
                    f"Превышено максимальное количество попыток проверки статуса генерации Kandinsky: {last_exception}",
                    original_error=last_exception,
                ) from last_exception
            else:
                raise APIError(
                    f"Превышено максимальное количество попыток проверки статуса генерации Kandinsky: {last_exception}",
                    original_error=last_exception,
                ) from last_exception
        else:
            raise APIError(
                "Превышено максимальное количество попыток проверки статуса генерации Kandinsky",
            )

    async def aclose(self) -> None:
        """Закрывает клиент и освобождает ресурсы.

        Закрывает HTTP-сессию и освобождает все связанные ресурсы.
        Должен вызываться при завершении работы приложения.
        """
        if hasattr(self, "_session") and self._session:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning(f"Ошибка при закрытии сессии KandinskyClient: {exc}")
            finally:
                self._session = None  # type: ignore[assignment]

    async def __aenter__(self) -> Self:
        """Вход в контекстный менеджер.

        Returns:
            Сам экземпляр клиента для использования в async with.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Выход из контекстного менеджера.

        Гарантированно вызывает aclose() даже при исключениях.

        Args:
            exc_type: Тип исключения (если было)
            exc_val: Экземпляр исключения (если было)
            exc_tb: Traceback (если было)
        """
        await self.aclose()
