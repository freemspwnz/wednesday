# Добавление новых эндпоинтов в HTTP-клиенты

Это руководство описывает, как добавлять новые методы для работы с API в HTTP-клиентах (`KandinskyClient`, `GigaChatTextClient` и других), использующих базовый класс `BaseHTTPClient`.

## Обзор

После внедрения базового класса `BaseHTTPClient` и helper-методов добавление нового эндпоинта стало значительно проще:

- **До рефакторинга:** ~50+ строк кода с дублированием логики
- **После рефакторинга:** 3-10 строк кода

## Быстрый старт

### Простой GET запрос с JSON

Самый простой случай — GET запрос, который возвращает JSON:

```python
async def get_pipeline_info(self, pipeline_id: str) -> dict[str, Any]:
    """Получает информацию о pipeline по ID.

    Args:
        pipeline_id: ID pipeline.

    Returns:
        Информация о pipeline.

    Raises:
        AuthenticationError: При ошибках аутентификации.
        NetworkError: При сетевых ошибках.
        APIError: При других ошибках API.
    """
    return await self._get_json(
        endpoint=f"key/api/v1/pipelines/{pipeline_id}",
        method_name="get_pipeline_info",
        headers=self._get_auth_headers(),
    )
```

**Что автоматически обрабатывается:**
- ✅ Формирование полного URL
- ✅ Retry логика через декоратор
- ✅ Обработка сетевых ошибок
- ✅ Парсинг JSON с валидацией статуса
- ✅ Логирование через retry декоратор

## Паттерны использования

### 1. Простой GET с JSON

Используйте `_get_json()` для простых GET запросов, возвращающих JSON:

```python
async def get_pipelines(self) -> list[dict[str, Any]]:
    """Получает список pipelines."""
    return await self._get_json(
        endpoint=self.ENDPOINT_PIPELINES,
        method_name="get_pipelines",
        headers=self._get_auth_headers(),
    )
```

### 2. GET с кастомной обработкой ответа

Если нужна дополнительная обработка ответа (валидация через Pydantic, преобразование данных):

```python
async def get_pipeline_info(self, pipeline_id: str) -> PipelineInfo:
    """Получает информацию о pipeline с типизированным результатом.

    Args:
        pipeline_id: ID pipeline.

    Returns:
        Типизированная информация о pipeline.

    Raises:
        ClientError: При ошибках запроса.
    """
    response = await self._get(
        endpoint=f"key/api/v1/pipelines/{pipeline_id}",
        method_name="get_pipeline_info",
        headers=self._get_auth_headers(),
    )
    async with response:
        data = await self._parse_json_response(response)
        return PipelineInfo.model_validate(data)
```

### 3. POST с JSON

Используйте `_post_json()` для POST запросов с JSON данными:

```python
async def update_pipeline_settings(
    self,
    pipeline_id: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Обновляет настройки pipeline.

    Args:
        pipeline_id: ID pipeline.
        settings: Новые настройки.

    Returns:
        Обновлённые настройки.

    Raises:
        ClientError: При ошибках запроса.
    """
    return await self._post_json(
        endpoint=f"key/api/v1/pipelines/{pipeline_id}/settings",
        method_name="update_pipeline_settings",
        headers=self._get_auth_headers(),
        json=settings,
    )
```

### 4. POST с FormData

Для загрузки файлов или отправки multipart/form-data:

```python
async def upload_image(self, image_data: bytes, filename: str) -> dict[str, Any]:
    """Загружает изображение через FormData.

    Args:
        image_data: Байты изображения.
        filename: Имя файла.

    Returns:
        Информация о загруженном файле.

    Raises:
        ClientError: При ошибках запроса.
    """
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
```

### 5. Запросы с кастомными заголовками

Передавайте дополнительные заголовки через параметр `headers`:

```python
async def get_with_custom_headers(self) -> dict[str, Any]:
    """Запрос с кастомными заголовками."""
    headers = self._get_auth_headers()
    headers["X-Custom-Header"] = "value"

    return await self._get_json(
        endpoint="key/api/v1/endpoint",
        method_name="get_with_custom_headers",
        headers=headers,
    )
```

### 6. Запросы с кастомными таймаутами

Используйте параметр `timeout` для установки кастомного таймаута:

```python
from aiohttp import ClientTimeout

async def get_with_timeout(self) -> dict[str, Any]:
    """Запрос с кастомным таймаутом."""
    timeout = ClientTimeout(total=30, connect=5)

    return await self._get_json(
        endpoint="key/api/v1/endpoint",
        method_name="get_with_timeout",
        headers=self._get_auth_headers(),
        timeout=timeout,
    )
```

### 7. Запросы с нестандартным статусом ответа

Если API возвращает успешный ответ с нестандартным статусом (например, 201 вместо 200):

```python
async def create_resource(self, data: dict[str, Any]) -> dict[str, Any]:
    """Создаёт ресурс (ожидает статус 201)."""
    response = await self._post(
        endpoint="key/api/v1/resources",
        method_name="create_resource",
        headers=self._get_auth_headers(),
        json=data,
    )
    async with response:
        return await self._parse_json_response(response, expected_status=201)
```

### 8. Безопасный парсинг JSON без проверки статуса

Если нужно получить данные из ответа независимо от статуса (например, для логирования):

```python
async def log_response(self) -> None:
    """Логирует ответ независимо от статуса."""
    response = await self._get(
        endpoint="key/api/v1/endpoint",
        method_name="log_response",
        headers=self._get_auth_headers(),
    )
    async with response:
        data = await self._safe_parse_json(response)
        if data:
            logger.info(f"Response data: {data}")
```

## Константы эндпоинтов

Рекомендуется добавлять константы для эндпоинтов в класс клиента для улучшения читаемости:

```python
class KandinskyClient(BaseHTTPClient, ITextToImageClient):
    # Константы эндпоинтов
    ENDPOINT_PIPELINES = "key/api/v1/pipelines"
    ENDPOINT_PIPELINE_INFO = "key/api/v1/pipelines/{pipeline_id}"
    ENDPOINT_PIPELINE_RUN = "key/api/v1/pipeline/run"
    ENDPOINT_PIPELINE_STATUS = "key/api/v1/pipeline/status"

    async def get_pipeline_info(self, pipeline_id: str) -> dict[str, Any]:
        """Получает информацию о pipeline."""
        return await self._get_json(
            endpoint=self.ENDPOINT_PIPELINE_INFO.format(pipeline_id=pipeline_id),
            method_name="get_pipeline_info",
            headers=self._get_auth_headers(),
        )
```

## Checklist для добавления нового метода

✅ **Checklist для добавления нового метода:**

1. **Определить тип запроса**
   - GET / POST / PUT / DELETE
   - Определить, нужен ли JSON ответ

2. **Определить эндпоинт**
   - Добавить константу эндпоинта в класс (если нужно)
   - Использовать форматирование строк для параметров

3. **Определить параметры метода**
   - Типизировать все параметры
   - Добавить docstring с описанием

4. **Определить тип возвращаемого значения**
   - `dict[str, Any]` для простых JSON ответов
   - `list[dict[str, Any]]` для списков
   - Pydantic модель для типизированных данных

5. **Выбрать helper-метод**
   - `_get_json()` / `_post_json()` для простых случаев
   - `_get()` / `_post()` + `_parse_json_response()` для кастомной обработки
   - `_safe_parse_json()` для безопасного парсинга без проверки статуса

6. **Добавить docstring**
   - Описание метода
   - Args для всех параметров
   - Returns с описанием возвращаемого значения
   - Raises с перечислением возможных исключений

7. **Добавить тесты**
   - Unit-тесты с моками
   - Проверка успешных случаев
   - Проверка обработки ошибок

8. **Обновить интерфейс (если нужно)**
   - Если метод должен быть частью публичного API, добавить в соответствующий Protocol

## Примеры улучшений

### До рефакторинга (~50 строк)

```python
async def get_pipeline_info(self, pipeline_id: str) -> dict[str, Any] | None:
    bound = logger.bind(event="kandinsky_get_pipeline_info", pipeline_id=pipeline_id)

    try:
        headers = self._get_auth_headers()
    except ValueError as exc:
        bound.error("API ключи не сконфигурированы: {}", str(exc))
        return None

    timeout = aiohttp.ClientTimeout(
        total=TIMEOUT_CHECK_TOTAL_SECONDS,
        connect=TIMEOUT_CHECK_CONNECT_SECONDS,
        sock_read=TIMEOUT_CHECK_SOCK_READ_SECONDS,
    )

    @retry_standard(service_name="kandinsky", method_name="get_pipeline_info")
    async def _fetch_pipeline_info() -> aiohttp.ClientResponse:
        return await self._session.get(
            f"{self._base_url}/key/api/v1/pipelines/{pipeline_id}",
            headers=headers,
            timeout=timeout,
        )

    try:
        async with await _fetch_pipeline_info() as response:
            if response.status == HTTP_STATUS_OK:
                data = await response.json()
                return data
            else:
                bound.error("Ошибка API: {}", response.status)
                return None
    except aiohttp.ClientConnectorError as exc:
        bound.error("Ошибка подключения: {}", str(exc))
        return None
    except Exception as exc:
        bound.error("Неожиданная ошибка: {}", str(exc))
        return None
```

### После рефакторинга (~3 строки)

```python
async def get_pipeline_info(self, pipeline_id: str) -> dict[str, Any]:
    """Получает информацию о pipeline по ID."""
    return await self._get_json(
        endpoint=f"key/api/v1/pipelines/{pipeline_id}",
        method_name="get_pipeline_info",
        headers=self._get_auth_headers(),
    )
```

**Улучшение:** ~50 строк → ~3 строки (упрощение в 16 раз)

## Доступные helper-методы

### `_get_json()` / `_post_json()`

Удобные методы для паттерна "запрос + парсинг JSON":

```python
async def _get_json(
    self,
    endpoint: str,
    method_name: str,
    headers: dict[str, str] | None = None,
    timeout: aiohttp.ClientTimeout | None = None,
    expected_status: int = 200,
    **kwargs: Any,
) -> dict[str, Any] | list[dict[str, Any]]
```

### `_parse_json_response()`

Парсит JSON ответ с валидацией статуса:

```python
async def _parse_json_response(
    self,
    response: aiohttp.ClientResponse,
    expected_status: int = 200,
) -> dict[str, Any] | list[dict[str, Any]]
```

### `_safe_parse_json()`

Безопасно парсит JSON без проверки статуса:

```python
async def _safe_parse_json(
    self,
    response: aiohttp.ClientResponse,
) -> dict[str, Any] | list[dict[str, Any]] | None
```

### `_get_response_text()`

Получает текст ответа с ограничением длины:

```python
async def _get_response_text(
    self,
    response: aiohttp.ClientResponse,
    max_length: int = 1000,
) -> str
```

## Обработка ошибок

Все helper-методы автоматически обрабатывают ошибки и пробрасывают доменные исключения:

- `AuthenticationError` — при ошибках аутентификации (401, 403)
- `RateLimitError` — при превышении лимита запросов (429)
- `NetworkError` — при сетевых ошибках (таймаут, ошибка соединения)
- `APIError` — при других ошибках API (4xx, 5xx)

Вам не нужно обрабатывать эти ошибки вручную — они автоматически пробрасываются из базового класса.

## Дополнительные ресурсы

- `services/clients/base.py` — базовый класс с helper-методами
- `services/clients/kandinsky.py` — примеры использования в KandinskyClient
- `services/clients/gigachat_text.py` — примеры использования в GigaChatTextClient
