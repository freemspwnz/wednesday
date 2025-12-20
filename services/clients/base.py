"""Базовый класс для HTTP-клиентов."""

from __future__ import annotations

from typing import Any

import aiohttp

from services.clients.exceptions import map_http_status_to_exception
from utils.retry import retry_standard


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
        """
        url = self._build_url(endpoint)
        request_headers = headers or {}
        request_timeout = timeout or self._default_timeout

        @retry_standard(service_name=self._service_name, method_name=method_name)
        async def _make_request() -> aiohttp.ClientResponse:
            return await self._session.get(
                url,
                headers=request_headers,
                timeout=request_timeout,
                **kwargs,
            )

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
        """
        url = self._build_url(endpoint)
        request_headers = headers or {}
        request_timeout = timeout or self._default_timeout

        @retry_standard(service_name=self._service_name, method_name=method_name)
        async def _make_request() -> aiohttp.ClientResponse:
            return await self._session.post(
                url,
                headers=request_headers,
                timeout=request_timeout,
                **kwargs,
            )

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
