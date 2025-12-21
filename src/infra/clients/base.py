"""Базовый класс для HTTP-клиентов."""

from __future__ import annotations

from typing import Any

import aiohttp

from infra.clients.sber_clients_exceptions import map_http_status_to_exception
from shared.base.exceptions import APIError, NetworkError
from shared.retry import retry_standard


class BaseHTTPClient:
    """Базовый класс для HTTP-клиентов с общей логикой запросов.

    Предоставляет методы для выполнения HTTP-запросов с общей обработкой ошибок,
    retry логикой и валидацией ответов.
    """

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession,
        service_name: str,
        default_timeout: aiohttp.ClientTimeout | None = None,
    ) -> None:
        """Инициализирует базовый HTTP-клиент.

        Args:
            base_url: Базовый URL API.
            session: Сессия aiohttp для выполнения запросов.
            service_name: Имя сервиса для логирования и retry.
            default_timeout: Таймаут по умолчанию для запросов (опционально).
        """
        self._base_url = base_url
        self._session = session
        self._service_name = service_name
        self._default_timeout = default_timeout

    def _build_url(self, endpoint: str) -> str:
        """Формирует полный URL из базового URL и эндпоинта.

        Args:
            endpoint: Эндпоинт API (например, "/key/api/v1/pipelines" или "key/api/v1/pipelines").
                Если endpoint пустой, возвращает base_url.
                Если endpoint начинается с "http://" или "https://", возвращает его как есть (полный URL).

        Returns:
            Полный URL для запроса.
        """
        # Если endpoint пустой, возвращаем base_url
        if not endpoint:
            return self._base_url

        # Если endpoint уже полный URL, возвращаем его как есть
        if endpoint.startswith(("http://", "https://")):
            return endpoint

        # Убираем лишние слэши
        base = self._base_url.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base}/{endpoint}"

    def _get_auth_headers(self) -> dict[str, str]:
        """Формирует заголовки авторизации.

        Должен быть переопределён в подклассах.

        Raises:
            NotImplementedError: Если метод не переопределён.
        """
        raise NotImplementedError("Подклассы должны реализовать _get_auth_headers()")

    async def _get(
        self,
        endpoint: str,
        method_name: str,
        headers: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> aiohttp.ClientResponse:
        """Выполняет GET запрос к API.

        Args:
            endpoint: Эндпоинт API.
            method_name: Имя метода для логирования и retry.
            headers: Дополнительные заголовки (опционально).
            timeout: Таймаут для запроса (опционально, используется default_timeout если не указан).
            **kwargs: Дополнительные параметры для aiohttp.ClientSession.get().

        Returns:
            Ответ от API.

        Raises:
            ClientError: При ошибках запроса.

        Example:
            GET запрос с кастомной обработкой::

                response = await self._get(
                    endpoint="key/api/v1/pipelines",
                    method_name="get_pipelines",
                    headers=self._get_auth_headers(),
                )
                async with response:
                    data = await self._parse_json_response(response)
        """
        url = self._build_url(endpoint)
        request_headers = headers or {}
        request_timeout = timeout or self._default_timeout

        @retry_standard(service_name=self._service_name, method_name=method_name)
        async def _make_request() -> aiohttp.ClientResponse:
            try:
                return await self._session.get(
                    url,
                    headers=request_headers,
                    timeout=request_timeout,
                    **kwargs,
                )
            except aiohttp.ClientConnectorError as exc:
                raise NetworkError(
                    f"Ошибка подключения к {self._service_name}: {exc}",
                    original_error=exc,
                ) from exc
            except aiohttp.ServerTimeoutError as exc:
                raise NetworkError(
                    f"Таймаут запроса к {self._service_name}: {exc}",
                    original_error=exc,
                ) from exc
            except TimeoutError as exc:
                raise NetworkError(
                    f"Таймаут при запросе к {self._service_name}",
                    original_error=exc,
                ) from exc

        return await _make_request()

    async def _post(
        self,
        endpoint: str,
        method_name: str,
        headers: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> aiohttp.ClientResponse:
        """Выполняет POST запрос к API.

        Args:
            endpoint: Эндпоинт API.
            method_name: Имя метода для логирования и retry.
            headers: Дополнительные заголовки (опционально).
            timeout: Таймаут для запроса (опционально, используется default_timeout если не указан).
            **kwargs: Дополнительные параметры для aiohttp.ClientSession.post().

        Returns:
            Ответ от API.

        Raises:
            ClientError: При ошибках запроса.

        Example:
            POST запрос с FormData::

                form_data = aiohttp.FormData()
                form_data.add_field("file", image_data, filename=filename)
                response = await self._post(
                    endpoint="key/api/v1/upload",
                    method_name="upload_image",
                    headers=self._get_auth_headers(),
                    data=form_data,
                )
                async with response:
                    return await self._parse_json_response(response)
        """
        url = self._build_url(endpoint)
        request_headers = headers or {}
        request_timeout = timeout or self._default_timeout

        @retry_standard(service_name=self._service_name, method_name=method_name)
        async def _make_request() -> aiohttp.ClientResponse:
            try:
                return await self._session.post(
                    url,
                    headers=request_headers,
                    timeout=request_timeout,
                    **kwargs,
                )
            except aiohttp.ClientConnectorError as exc:
                raise NetworkError(
                    f"Ошибка подключения к {self._service_name}: {exc}",
                    original_error=exc,
                ) from exc
            except aiohttp.ServerTimeoutError as exc:
                raise NetworkError(
                    f"Таймаут запроса к {self._service_name}: {exc}",
                    original_error=exc,
                ) from exc
            except TimeoutError as exc:
                raise NetworkError(
                    f"Таймаут при запросе к {self._service_name}",
                    original_error=exc,
                ) from exc

        return await _make_request()

    async def _validate_response(
        self,
        response: aiohttp.ClientResponse,
        expected_status: int = 200,
    ) -> None:
        """Валидирует ответ API и пробрасывает исключение при ошибках.

        Args:
            response: Ответ от API.
            expected_status: Ожидаемый HTTP статус (по умолчанию 200).

        Raises:
            AuthenticationError: При ошибках аутентификации (401, 403).
            RateLimitError: При превышении лимита запросов (429).
            NetworkError: При сетевых ошибках.
            APIError: При других ошибках API.
        """
        if response.status != expected_status:
            error_text = await response.text()
            exception = map_http_status_to_exception(
                status_code=response.status,
                message=f"Ошибка API {self._service_name}: HTTP {response.status}",
                response_body=error_text,
                response=response,
            )
            raise exception

    async def _parse_json_response(
        self,
        response: aiohttp.ClientResponse,
        expected_status: int = 200,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Парсит JSON ответ и проверяет статус.

        Args:
            response: Ответ от API.
            expected_status: Ожидаемый HTTP статус (по умолчанию 200).

        Returns:
            Распарсенные данные JSON (dict или list).

        Raises:
            AuthenticationError: При ошибках аутентификации (401, 403).
            RateLimitError: При превышении лимита запросов (429).
            APIError: При других ошибках API (4xx, 5xx).
            ValueError: При ошибках парсинга JSON.

        Example:
            GET запрос с кастомной обработкой ответа::

                async def get_pipeline_info(self, pipeline_id: str) -> PipelineInfo:
                    response = await self._get(
                        endpoint=f"key/api/v1/pipelines/{pipeline_id}",
                        method_name="get_pipeline_info",
                        headers=self._get_auth_headers(),
                    )
                    async with response:
                        data = await self._parse_json_response(response)
                        return PipelineInfo.model_validate(data)
        """
        if response.status != expected_status:
            error_text = await response.text()
            exception = map_http_status_to_exception(
                status_code=response.status,
                message=f"Ошибка API {self._service_name}: HTTP {response.status}",
                response_body=error_text,
                response=response,
            )
            raise exception

        try:
            return await response.json()  # type: ignore[no-any-return]
        except aiohttp.ContentTypeError as exc:
            error_text = await response.text()
            raise APIError(
                f"Ошибка парсинга JSON от {self._service_name}: ответ не является JSON",
                original_error=exc,
            ) from exc

    async def _safe_parse_json(  # noqa: PLR6301
        self,
        response: aiohttp.ClientResponse,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Безопасно парсит JSON ответ без проверки статуса.

        Используется для случаев, когда нужно получить данные из ответа
        независимо от статуса (например, для логирования).

        Args:
            response: Ответ от API.

        Returns:
            Распарсенные данные JSON или None при ошибке парсинга.
        """
        try:
            return await response.json()  # type: ignore[no-any-return]
        except (aiohttp.ContentTypeError, ValueError):
            return None

    async def _get_response_text(  # noqa: PLR6301
        self,
        response: aiohttp.ClientResponse,
        max_length: int = 1000,
    ) -> str:
        """Получает текст ответа с ограничением длины.

        Args:
            response: Ответ от API.
            max_length: Максимальная длина текста (по умолчанию 1000).

        Returns:
            Текст ответа (обрезанный до max_length символов).
        """
        text = await response.text()
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    async def _get_json(
        self,
        endpoint: str,
        method_name: str,
        headers: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        expected_status: int = 200,
        **kwargs: Any,  # noqa: ANN401
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Выполняет GET запрос и парсит JSON ответ.

        Удобный метод для частого паттерна "запрос + парсинг JSON".

        Args:
            endpoint: Эндпоинт API.
            method_name: Имя метода для логирования и retry.
            headers: Дополнительные заголовки (опционально).
            timeout: Таймаут для запроса (опционально).
            expected_status: Ожидаемый HTTP статус (по умолчанию 200).
            **kwargs: Дополнительные параметры для aiohttp.ClientSession.get().

        Returns:
            Распарсенные данные JSON.

        Raises:
            ClientError: При ошибках запроса или парсинга.

        Example:
            Простой GET запрос с JSON ответом::

                async def get_pipeline_info(self, pipeline_id: str) -> dict[str, Any]:
                    return await self._get_json(
                        endpoint=f"key/api/v1/pipelines/{pipeline_id}",
                        method_name="get_pipeline_info",
                        headers=self._get_auth_headers(),
                    )
        """
        response = await self._get(
            endpoint=endpoint,
            method_name=method_name,
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
        async with response:
            return await self._parse_json_response(response, expected_status=expected_status)

    async def _post_json(
        self,
        endpoint: str,
        method_name: str,
        headers: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        expected_status: int = 200,
        **kwargs: Any,  # noqa: ANN401
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Выполняет POST запрос и парсит JSON ответ.

        Удобный метод для частого паттерна "запрос + парсинг JSON".

        Args:
            endpoint: Эндпоинт API.
            method_name: Имя метода для логирования и retry.
            headers: Дополнительные заголовки (опционально).
            timeout: Таймаут для запроса (опционально).
            expected_status: Ожидаемый HTTP статус (по умолчанию 200).
            **kwargs: Дополнительные параметры для aiohttp.ClientSession.post().

        Returns:
            Распарсенные данные JSON.

        Raises:
            ClientError: При ошибках запроса или парсинга.

        Example:
            POST запрос с JSON данными::

                async def update_settings(
                    self, pipeline_id: str, settings: dict[str, Any]
                ) -> dict[str, Any]:
                    return await self._post_json(
                        endpoint=f"key/api/v1/pipelines/{pipeline_id}/settings",
                        method_name="update_settings",
                        headers=self._get_auth_headers(),
                        json=settings,
                    )
        """
        response = await self._post(
            endpoint=endpoint,
            method_name=method_name,
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
        async with response:
            return await self._parse_json_response(response, expected_status=expected_status)
