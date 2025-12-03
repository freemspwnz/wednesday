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
from typing import Any

import aiohttp
from loguru import logger
from PIL import Image

from services.clients import ITextToImageClient
from utils.config import config
from utils.retry import retry_standard

HTTP_STATUS_OK = 200
HTTP_STATUS_UNAUTHORIZED = 401
HTTP_STATUS_FORBIDDEN = 403

TIMEOUT_GENERATION_TOTAL_SECONDS = config.generation_timeout
TIMEOUT_GENERATION_CONNECT_SECONDS = 10
TIMEOUT_GENERATION_SOCK_READ_SECONDS = 30

TIMEOUT_CHECK_TOTAL_SECONDS = 15
TIMEOUT_CHECK_CONNECT_SECONDS = 5
TIMEOUT_CHECK_SOCK_READ_SECONDS = 10

MAX_STATUS_ATTEMPTS = 10
STATUS_POLL_DELAY_SECONDS = 10


class KandinskyClient(ITextToImageClient):
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

    def __init__(self) -> None:
        self._api_key: str | None = config.kandinsky_api_key
        self._secret_key: str | None = config.kandinsky_secret_key
        self._base_url: str = "https://api-key.fusionbrain.ai"
        self._proxy_url: str | None = None

        # Proxy берём из стандартных переменных окружения, как и в старой реализации.
        import os

        self._proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

    # ------------------------------------------------------------------ #
    # Публичный интерфейс ITextToImageClient                             #
    # ------------------------------------------------------------------ #

    async def generate(self, prompt: str, user_id: str | None = None) -> bytes | None:
        """Генерирует изображение по текстовому промпту через Kandinsky API.

        Args:
            prompt: Текстовое описание изображения.
            user_id: Идентификатор пользователя (для логирования), опционально.

        Returns:
            Байты изображения PNG или None при ошибке.
        """
        bound = logger.bind(event="kandinsky_generate", user_id=user_id)
        bound.info("Запрос генерации изображения через Kandinsky API получен")

        try:
            headers = self._get_auth_headers()
        except ValueError as exc:
            bound.error("API ключи Kandinsky не сконфигурированы: {}", str(exc))
            return None

        timeout = aiohttp.ClientTimeout(
            total=TIMEOUT_GENERATION_TOTAL_SECONDS,
            connect=TIMEOUT_GENERATION_CONNECT_SECONDS,
            sock_read=TIMEOUT_GENERATION_SOCK_READ_SECONDS,
        )

        connector: aiohttp.BaseConnector | None = None
        if self._proxy_url:
            # ProxyConnector не типизирован стабильно в aiohttp, поэтому игнорируем attr‑check.
            connector = aiohttp.ProxyConnector.from_url(self._proxy_url)  # type: ignore[attr-defined]
            bound.bind(proxy_url=self._proxy_url).info("Используется прокси для запроса к Kandinsky")

        try:
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                pipeline_id = await self._get_pipeline_id(session, headers, user_id=user_id)
                if not pipeline_id:
                    bound.error("Не удалось получить pipeline ID для генерации изображения")
                    return None

                uuid = await self._start_generation(session, headers, pipeline_id, prompt, user_id=user_id)
                if not uuid:
                    bound.error("Kandinsky не вернул UUID задачи генерации")
                    return None

                image_data = await self._wait_for_generation(session, headers, uuid, user_id=user_id)
                if image_data is None:
                    bound.error("Не удалось получить итоговое изображение от Kandinsky")
                    return None

                # В логах не показываем бинарные данные, только размеры.
                bound.bind(image_size_bytes=len(image_data)).info(
                    "Изображение успешно получено от Kandinsky",
                )
                return image_data
        except TimeoutError:
            bound.error("Таймаут верхнего уровня при генерации изображения через Kandinsky")
            return None
        except aiohttp.ClientConnectorError as exc:
            bound.error(
                "Ошибка подключения к Kandinsky API: {}. Возможные причины: проблемы с сетью, "
                "недоступность сервера или прокси.",
                str(exc),
            )
            return None
        except aiohttp.ClientError as exc:
            bound.error("Ошибка клиента aiohttp при запросе к Kandinsky API: {}", str(exc))
            return None
        except Exception as exc:  # pragma: no cover - защитный фоллбек
            bound.bind(error=str(exc)).error(
                "Неожиданная ошибка при генерации изображения через Kandinsky",
            )
            return None

    # ------------------------------------------------------------------ #
    # Дополнительные методы для healthcheck и админ‑команд               #
    # ------------------------------------------------------------------ #

    async def check_api_status(
        self,
        save_models: bool = True,
    ) -> tuple[bool, str, list[str], tuple[str | None, str | None]]:
        """Dry‑run проверка статуса API и валидности ключей без генерации.

        Возвращает флаг успеха, человекочитаемое сообщение, список моделей
        и пару (текущий_pipeline_id, текущее_имя).
        """
        bound = logger.bind(event="kandinsky_status_check")
        bound.debug("Начало проверки статуса Kandinsky (save_models={})", save_models)

        try:
            headers = self._get_auth_headers()
        except ValueError as exc:
            msg = f"❌ Ошибка конфигурации ключей: {str(exc)[:50]}"
            bound.bind(error=str(exc)).error(msg)
            return False, msg, [], (None, None)

        timeout = aiohttp.ClientTimeout(
            total=TIMEOUT_CHECK_TOTAL_SECONDS,
            connect=TIMEOUT_CHECK_CONNECT_SECONDS,
            sock_read=TIMEOUT_CHECK_SOCK_READ_SECONDS,
        )

        connector: aiohttp.BaseConnector | None = None
        if self._proxy_url:
            connector = aiohttp.ProxyConnector.from_url(self._proxy_url)  # type: ignore[attr-defined]

        @retry_standard(service_name="kandinsky", method_name="check_api_status")
        async def _fetch_pipelines_status(session: aiohttp.ClientSession) -> aiohttp.ClientResponse:
            return await session.get(f"{self._base_url}/key/api/v1/pipelines", headers=headers)

        try:
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                from utils.models_store import ModelsStore

                models_store = ModelsStore()
                current_pipeline_id, current_pipeline_name = await models_store.get_kandinsky_model()

                bound.debug("Запрос списка pipelines для dry‑run статуса")
                async with await _fetch_pipelines_status(session) as response:
                    status_ok = False
                    status_message = "❌ Ошибка проверки"
                    models_list: list[str] = []

                    if response.status == HTTP_STATUS_OK:
                        status_ok = True
                        status_message = "✅ API доступен, ключ валиден"
                        pipelines_data = await response.json()
                        if isinstance(pipelines_data, list) and pipelines_data:
                            if save_models:
                                await models_store.set_kandinsky_available_models(pipelines_data)
                                bound.debug(
                                    "Сохранён список из {} моделей Kandinsky",
                                    len(pipelines_data),
                                )

                            for pipeline in pipelines_data:
                                model_name = str(pipeline.get("name", "Unknown"))
                                model_id = str(pipeline.get("id", "N/A"))
                                is_current = " ⭐" if (current_pipeline_id and model_id == current_pipeline_id) else ""
                                models_list.append(f"{model_name} (ID: {model_id}){is_current}")
                        else:
                            models_list = ["Модели не найдены"]
                    elif response.status == HTTP_STATUS_UNAUTHORIZED:
                        status_message = "❌ Неверный API ключ или секретный ключ"
                        models_list = ["Требуется проверка авторизации"]
                    elif response.status == HTTP_STATUS_FORBIDDEN:
                        status_message = "❌ Доступ запрещён (проверьте права ключа)"
                        models_list = ["Нет доступа к моделям"]
                    else:
                        status_message = f"⚠️  Ошибка API: {response.status}"
                        models_list = [f"Ошибка получения моделей: {response.status}"]

                bound.debug(
                    "Завершена проверка статуса Kandinsky: ok={}, models={}, current=({}, {})",
                    status_ok,
                    len(models_list),
                    current_pipeline_id,
                    current_pipeline_name,
                )
                return status_ok, status_message, models_list, (current_pipeline_id, current_pipeline_name)
        except TimeoutError:
            return False, "❌ Таймаут при подключении к API", [], (None, None)
        except Exception as exc:  # pragma: no cover - защитный фоллбек
            return False, f"❌ Ошибка подключения: {str(exc)[:50]}", [], (None, None)

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Возвращает список доступных моделей Kandinsky.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Список доступных моделей в формате "Name (ID: xxx)" или пустой список при ошибке.
        """
        bound = logger.bind(event="kandinsky_get_available_models", save_models=save_models)
        bound.debug("Запрос списка доступных моделей Kandinsky")

        # Пытаемся получить через check_api_status, который уже возвращает список моделей
        try:
            _status_ok, _status_msg, models_list, _current = await self.check_api_status(save_models=save_models)
            if models_list:
                bound.debug("Получен список из {} моделей через check_api_status", len(models_list))
                return models_list
        except Exception as exc:
            bound.warning("Не удалось получить модели через check_api_status: {}", str(exc))

        # Fallback: пытаемся получить из хранилища
        try:
            from utils.models_store import ModelsStore

            models_store = ModelsStore()
            stored_models = await models_store.get_kandinsky_available_models()
            if stored_models:
                bound.debug("Получен список из {} моделей из хранилища", len(stored_models))
                return stored_models
        except Exception as exc:
            bound.warning("Не удалось получить модели из хранилища: {}", str(exc))

        # Если ничего не получилось, возвращаем пустой список
        bound.warning("Не удалось получить список моделей, возвращаем пустой список")
        return []

    async def set_model(self, model_identifier: str) -> tuple[bool, str]:
        """Устанавливает текущую модель (pipeline) по ID или части названия.

        Этот метод является унифицированным интерфейсом ITextToImageClient.
        """
        bound = logger.bind(event="kandinsky_set_model", model_identifier=model_identifier)

        try:
            headers = self._get_auth_headers()
        except ValueError as exc:
            msg = f"Ошибка конфигурации ключей: {str(exc)[:50]}"
            bound.bind(error=str(exc)).error(msg)
            return False, msg

        timeout = aiohttp.ClientTimeout(
            total=TIMEOUT_CHECK_TOTAL_SECONDS,
            connect=TIMEOUT_CHECK_CONNECT_SECONDS,
            sock_read=TIMEOUT_CHECK_SOCK_READ_SECONDS,
        )

        connector: aiohttp.BaseConnector | None = None
        if self._proxy_url:
            connector = aiohttp.ProxyConnector.from_url(self._proxy_url)  # type: ignore[attr-defined]

        @retry_standard(service_name="kandinsky", method_name="set_model")
        async def _fetch_pipelines_for_set_model(session: aiohttp.ClientSession) -> aiohttp.ClientResponse:
            return await session.get(f"{self._base_url}/key/api/v1/pipelines", headers=headers)

        try:
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with await _fetch_pipelines_for_set_model(session) as response:
                    if response.status != HTTP_STATUS_OK:
                        msg = f"Ошибка API при получении списка моделей: {response.status}"
                        bound.error(msg)
                        return False, msg

                    pipelines_data = await response.json()
                    if not isinstance(pipelines_data, list):
                        return False, "Не удалось получить список моделей"

                    # 1. Точное совпадение по ID.
                    for pipeline_item in pipelines_data:
                        if pipeline_item.get("id") == model_identifier:
                            matched_model_name = str(pipeline_item.get("name", "Unknown"))
                            matched_pipeline_id = str(pipeline_item.get("id", ""))
                            from utils.models_store import ModelsStore

                            models_store = ModelsStore()
                            await models_store.set_kandinsky_model(matched_pipeline_id, matched_model_name)
                            msg = f"Модель установлена: {matched_model_name} (ID: {matched_pipeline_id})"
                            bound.info(msg)
                            return True, msg

                    # 2. Частичное совпадение по названию (регистронезависимо).
                    model_identifier_lower = model_identifier.lower()
                    matches: list[dict[str, Any]] = []
                    for pipeline_item in pipelines_data:
                        pipeline_name = str(pipeline_item.get("name", ""))
                        if model_identifier_lower in pipeline_name.lower():
                            matches.append(pipeline_item)

                    if len(matches) == 1:
                        matched_pipeline = matches[0]
                        selected_model_name = str(matched_pipeline.get("name", "Unknown"))
                        selected_pipeline_id = str(matched_pipeline.get("id", ""))
                        from utils.models_store import ModelsStore

                        models_store = ModelsStore()
                        await models_store.set_kandinsky_model(selected_pipeline_id, selected_model_name)
                        msg = f"Модель установлена: {selected_model_name} (ID: {selected_pipeline_id})"
                        bound.info(msg)
                        return True, msg

                    if len(matches) > 1:
                        models_list = [f"{p.get('name', 'Unknown')!s} (ID: {p.get('id', 'N/A')!s})" for p in matches]
                        msg = (
                            "Найдено несколько моделей:\n"
                            + "\n".join(models_list)
                            + "\n\nУточните название или используйте ID"
                        )
                        bound.warning("Несколько моделей соответствуют запросу: {}", models_list)
                        return False, msg

                    msg = (
                        f"Модель '{model_identifier}' не найдена. Используйте /status для просмотра доступных моделей."
                    )
                    bound.warning(msg)
                    return False, msg
        except Exception as exc:  # pragma: no cover - защитный фоллбек
            bound.bind(error=str(exc)).error("Ошибка при установке модели Kandinsky")
            return False, f"Ошибка: {str(exc)[:50]}"

    # ------------------------------------------------------------------ #
    # Внутренние helpers                                                 #
    # ------------------------------------------------------------------ #

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

    async def _get_pipeline_id(
        self,
        session: aiohttp.ClientSession,
        headers: dict[str, str],
        *,
        user_id: str | None = None,
    ) -> str | None:
        """Выбирает актуальный pipeline ID, используя сохранённую модель или первую доступную."""
        from utils.models_store import ModelsStore

        bound = logger.bind(event="kandinsky_get_pipeline", user_id=user_id)
        models_store = ModelsStore()
        saved_pipeline_id, saved_pipeline_name = await models_store.get_kandinsky_model()

        @retry_standard(service_name="kandinsky", method_name="get_pipeline_id")
        async def _fetch_pipelines() -> aiohttp.ClientResponse:
            return await session.get(f"{self._base_url}/key/api/v1/pipelines", headers=headers)

        try:
            async with await _fetch_pipelines() as response:
                if response.status != HTTP_STATUS_OK:
                    bound.error("Ошибка при получении списка pipelines: HTTP {}", response.status)
                    return None

                data: list[dict[str, Any]] = await response.json()
                if not data:
                    bound.error("Пустой ответ при получении pipelines от Kandinsky")
                    return None

                if saved_pipeline_id:
                    for pipeline in data:
                        if pipeline.get("id") == saved_pipeline_id:
                            bound.bind(
                                pipeline_id=saved_pipeline_id,
                                pipeline_name=saved_pipeline_name,
                            ).info("Используется сохранённая модель Kandinsky")
                            return saved_pipeline_id

                    bound.warning(
                        "Сохранённая модель {} не найдена среди доступных; используется первая доступная.",
                        saved_pipeline_id,
                    )

                pipeline_id_raw = data[0].get("id")
                pipeline_name_raw = data[0].get("name", "Unknown")
                pipeline_id = str(pipeline_id_raw) if pipeline_id_raw is not None else ""
                pipeline_name = str(pipeline_name_raw)
                await models_store.set_kandinsky_model(pipeline_id, pipeline_name)
                bound.bind(pipeline_id=pipeline_id, pipeline_name=pipeline_name).info(
                    "Выбран pipeline для генерации через Kandinsky",
                )
                return pipeline_id
        except aiohttp.ClientConnectorError as exc:
            bound.error(
                "Ошибка подключения к Kandinsky API при получении pipeline ID: {}",
                str(exc),
            )
            return None
        except aiohttp.ClientError as exc:
            bound.error("Ошибка клиента при получении pipeline ID: {}", str(exc))
            return None
        except TimeoutError:
            bound.error("Таймаут при получении pipeline ID от Kandinsky")
            return None
        except Exception as exc:  # pragma: no cover - защитный фоллбек
            bound.bind(error=str(exc)).error(
                "Неожиданная ошибка при получении pipeline ID от Kandinsky",
            )
            return None

    async def _start_generation(
        self,
        session: aiohttp.ClientSession,
        headers: dict[str, str],
        pipeline_id: str,
        prompt: str,
        *,
        user_id: str | None = None,
    ) -> str | None:
        """Создаёт задачу генерации и возвращает UUID."""
        bound = logger.bind(event="kandinsky_start_generation", user_id=user_id, pipeline_id=pipeline_id)

        params = {
            "type": "GENERATE",
            "numImages": 1,
            "width": 1024,
            "height": 1024,
            "generateParams": {
                "query": prompt,
            },
        }

        import json

        form_data = aiohttp.FormData()
        form_data.add_field("pipeline_id", pipeline_id)
        # Параметры передаём как JSON‑строку, как того требует API Fusion Brain.
        form_data.add_field("params", json.dumps(params), content_type="application/json")

        @retry_standard(service_name="kandinsky", method_name="start_generation")
        async def _post_generation() -> aiohttp.ClientResponse:
            return await session.post(
                f"{self._base_url}/key/api/v1/pipeline/run",
                headers=headers,
                data=form_data,
            )

        try:
            async with await _post_generation() as response:
                if response.status in {200, 201}:
                    result = await response.json()
                    uuid_value = result.get("uuid")
                    if not uuid_value:
                        bound.error("Успешный HTTP‑ответ без UUID задачи генерации")
                        return None
                    uuid_str = str(uuid_value)
                    bound.bind(task_uuid=uuid_str).info("Задача генерации на Kandinsky успешно создана")
                    return uuid_str

                error_text = await response.text()
                bound.bind(
                    http_status=response.status,
                    error_text=error_text[:300],
                ).error("Ошибка при запуске генерации на Kandinsky")
                return None
        except aiohttp.ClientConnectorError as exc:
            bound.error(
                "Ошибка подключения к Kandinsky API при запуске генерации: {}",
                str(exc),
            )
            return None
        except aiohttp.ClientError as exc:
            bound.error("Ошибка клиента при запуске генерации на Kandinsky: {}", str(exc))
            return None
        except Exception as exc:  # pragma: no cover - защитный фоллбек
            bound.bind(error=str(exc)).error("Неожиданная ошибка при запуске генерации на Kandinsky")
            return None

    async def _wait_for_generation(
        self,
        session: aiohttp.ClientSession,
        headers: dict[str, str],
        uuid: str,
        *,
        user_id: str | None = None,
    ) -> bytes | None:
        """Ожидает завершения задачи генерации и возвращает байты изображения."""
        bound = logger.bind(event="kandinsky_poll_generation", user_id=user_id, task_uuid=uuid)

        @retry_standard(service_name="kandinsky", method_name="wait_for_generation_status")
        async def _fetch_status() -> aiohttp.ClientResponse:
            return await session.get(
                f"{self._base_url}/key/api/v1/pipeline/status/{uuid}",
                headers=headers,
            )

        for attempt in range(1, MAX_STATUS_ATTEMPTS + 1):
            try:
                async with await _fetch_status() as response:
                    if response.status != HTTP_STATUS_OK:
                        bound.bind(http_status=response.status, attempt=attempt).error(
                            "Ошибка при проверке статуса генерации на Kandinsky",
                        )
                        return None

                    data: dict[str, Any] = await response.json()
                    status = data.get("status")

                    if status == "DONE":
                        result = data.get("result", {})
                        files = result.get("files", [])
                        if not files:
                            bound.error("Ответ Kandinsky со статусом DONE без файлов результата")
                            return None

                        image_base64 = files[0]
                        try:
                            image_data = base64.b64decode(image_base64)
                        except Exception as exc:  # pragma: no cover - практически не воспроизводится
                            bound.bind(error=str(exc)).error(
                                "Не удалось декодировать base64‑изображение от Kandinsky",
                            )
                            return None

                        # Валидация, что это действительно изображение.
                        try:
                            Image.open(BytesIO(image_data))
                        except Exception as exc:
                            bound.bind(error=str(exc)).error(
                                "Полученные данные от Kandinsky не являются валидным изображением",
                            )
                            return None

                        bound.bind(attempt=attempt).info(
                            "Генерация изображения на Kandinsky завершена успешно",
                        )
                        return image_data

                    if status == "FAIL":
                        error_desc = data.get("errorDescription", "Неизвестная ошибка")
                        bound.bind(error_description=error_desc, attempt=attempt).error(
                            "Генерация на Kandinsky завершилась с ошибкой",
                        )
                        return None

                    if status in {"INITIAL", "PROCESSING"}:
                        bound.bind(status=status, attempt=attempt).info(
                            "Генерация на Kandinsky ещё выполняется, продолжаем ожидание",
                        )
                        await asyncio.sleep(STATUS_POLL_DELAY_SECONDS)
                        continue

                    bound.bind(raw_status=status, attempt=attempt).error(
                        "Kandinsky вернул неизвестный статус генерации",
                    )
                    return None

            except aiohttp.ClientConnectorError as exc:
                bound.bind(attempt=attempt, error=str(exc)).error(
                    "Ошибка подключения при проверке статуса генерации Kandinsky",
                )
            except aiohttp.ClientError as exc:
                bound.bind(attempt=attempt, error=str(exc)).error(
                    "Ошибка клиента при проверке статуса генерации Kandinsky",
                )
            except TimeoutError:
                bound.bind(attempt=attempt).warning(
                    "Таймаут при проверке статуса генерации Kandinsky",
                )
            except Exception as exc:  # pragma: no cover - защитный фоллбек
                bound.bind(attempt=attempt, error=str(exc)).error(
                    "Неожиданная ошибка при проверке статуса генерации Kandinsky",
                )

            if attempt < MAX_STATUS_ATTEMPTS:
                await asyncio.sleep(STATUS_POLL_DELAY_SECONDS)

        bound.error(
            "Превышено максимальное количество попыток проверки статуса генерации Kandinsky ({} попыток)",
            MAX_STATUS_ATTEMPTS,
        )
        return None

    async def aclose(self) -> None:
        """
        Закрывает клиент и освобождает ресурсы.

        В текущей реализации KandinskyClient не использует долгоживущие соединения
        (сессии создаются в контекстных менеджерах и автоматически закрываются),
        поэтому метод оставлен пустым для консистентности интерфейса с другими
        клиентами и возможности расширения в будущем.
        """
        # В текущей реализации не требуется явного закрытия ресурсов,
        # так как все aiohttp.ClientSession создаются в контекстных менеджерах
        # и автоматически закрываются. Метод добавлен для консистентности
        # интерфейса и поддержки паттерна динамической замены клиентов.
        pass
