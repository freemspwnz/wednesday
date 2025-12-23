"""
Клиент для работы с API GigaChat.

Этот модуль инкапсулирует всю сетевую/HTTP‑логику:

- получение access token через OAuth2;
- запросы к эндпоинтам `/chat/completions` и `/models`;
- парсинг ответов и базовую валидацию;
- обработку сетевых ошибок и таймаутов;
- кэширование токенов до истечения срока действия.

Бизнес‑логика генерации промптов (сохранение в файлы, кеш, метрики)
остаётся в `services.image_generator.ImageGenerator` или других сервисах.
Они используют этот клиент через абстракцию `ITextToTextClient`.

Используем Loguru для структурированного логирования:

- базовый логгер конфигурируется в `utils.logger`;
- для сетевых событий создаём "обогащённый" логгер через
  `logger.bind(event="...", user_id=user_id)` и пишем краткие текстовые
  сообщения без чувствительных данных;
- JSON‑sink Loguru автоматически добавляет все bound‑поля в структуру лога,
  что упрощает анализ запросов и ошибок по полям `event`, `user_id`,
  `status`, `attempt` и т.п.
"""

from __future__ import annotations

import ssl
import time
import uuid
from types import TracebackType
from typing import Final, Self

import aiohttp
from loguru import logger
from pydantic import ValidationError

from infra.clients.base import BaseHTTPClient
from infra.clients.models import (
    APIStatusResult,
    GigaChatCompletionResponse,
    GigaChatModelInfo,
    GigaChatModelsListResponse,
    GigaChatTokenResponse,
    SetModelResult,
)
from infra.clients.sber_clients_exceptions import map_client_errors
from shared.base.exceptions import APIError, AuthenticationError, NetworkError, RateLimitError
from shared.config import GigaChatConfig
from shared.protocols import IModelsRepo, ITextToTextClient

HTTP_STATUS_OK: Final[int] = 200
TOKEN_EXPIRY_BUFFER_SECONDS: Final[int] = 300
DEFAULT_EXPIRES_IN_SECONDS: Final[int] = 1800
MAX_TOKENS_DEFAULT: Final[int] = 300
MAX_ERROR_TEXT_LENGTH: Final[int] = 100
AUTH_KEY_PREVIEW_LENGTH: Final[int] = 10

# Системное сообщение для генерации промптов Wednesday Frog
SYSTEM_MESSAGE = """Ты эксперт по созданию промптов для генерации изображений.
Создавай креативные, детальные и разнообразные промпты для генерации мемов Wednesday Frog (жаба по средам).
Каждый промпт должен быть уникальным, содержать детальное описание внешности жабы, позы, стиля и атмосферы.
Используй разнообразие в стилях: мультяшный, реалистичный, пиксель-арт, минимализм и т.д.
Промпт должен быть на английском языке, готовым для Kandinsky API.
Формат: детальное описание жабы, её действия/позы, стиль, атмосфера.
Примеры хороших промптов:
- "a cheerful cartoon green frog wearing a tiny blue hat, sitting on a mushroom, \
Wednesday meme style, vibrant colors, cute and friendly, digital art"
- "a cool green frog with sunglasses jumping in excitement, Wednesday my dudes meme, \
cartoon style, bright background, dynamic pose"
"""

USER_MESSAGE = (
    "Создай креативный и уникальный промпт для генерации изображения "
    "Wednesday Frog (жабы по средам) в стиле мема.\n"
    "Промпт должен быть:\n"
    "1. Детальным и конкретным\n"
    "2. Описывать внешность жабы (цвет, размер, особенности)\n"
    "3. Описывать действие или позу (сидит, прыгает, танцует и т.д.)\n"
    "4. Указывать стиль изображения (cartoon, realistic, pixel art, minimalistic, watercolor и т.д.)\n"
    "5. Описывать атмосферу и окружение\n"
    "6. Быть готовым для Kandinsky API (на английском языке)\n\n"
    "Важно: каждый промпт должен быть уникальным и разнообразным! Прояви креативность!\n"
    "Промпт должен быть одним предложением, готовым к использованию в Kandinsky API."
)

# Стандартные модели GigaChat для fallback
FALLBACK_MODELS = [
    "GigaChat",
    "GigaChat-2",
    "GigaChat-2-Max",
    "GigaChat-2-Pro",
    "GigaChat-Max",
    "GigaChat-Max-preview",
    "GigaChat-Plus",
    "GigaChat-Pro",
    "GigaChat-Pro-preview",
    "Embeddings",
    "Embeddings-2",
    "EmbeddingsGigaR",
]


class GigaChatTextClient(BaseHTTPClient, ITextToTextClient):
    """HTTP‑клиент GigaChat, реализующий интерфейс `ITextToTextClient`.

    Архитектурно клиент отвечает только за:

    - корректное обращение к HTTP‑эндпоинтам GigaChat;
    - авторизацию через OAuth2 и кэширование токенов;
    - выбор модели и генерацию текста;
    - обработку сетевых ошибок и таймаутов.

    Любые бизнес‑аспекты (сохранение промптов в файлы, кеш, Prometheus)
    реализуются на уровне сервисов, использующих этот клиент.
    """

    # Константы эндпоинтов (используются как относительные пути)
    # base_url будет установлен в __init__ на основе config.api_url

    def __init__(
        self,
        config: GigaChatConfig,
        models_repo: IModelsRepo,
    ) -> None:
        """Инициализация клиента GigaChat.

        Args:
            config: Конфигурация GigaChat клиента (обязательна).
            models_repo: Репозиторий моделей для сохранения/получения настроек моделей.
        """
        self._auth_url: str = config.auth_url
        self._api_url: str = config.api_url
        self._models_url: str = config.models_url
        self._authorization_key: str = config.authorization_key
        self._scope: str = config.scope
        self._verify_ssl: bool | str = config.verify_ssl
        self._model: str = config.model
        self._models_repo: IModelsRepo = models_repo
        self._config: GigaChatConfig = config

        # Кэш токена
        self._access_token: str | None = None
        self._token_expiry_time: float | None = None

        # Блокировка для конкурентного обновления токена.
        # Это гарантирует, что при большом числе одновременных запросов
        # не возникнет состояний гонки внутри aiohttp/коннектора.
        import asyncio

        self._token_lock: asyncio.Lock = asyncio.Lock()

        # Общий aiohttp.ClientSession на жизненный цикл клиента.
        # Таймауты и SSL‑контекст задаются один раз.
        self._timeout = config.prompt_timeout.to_client_timeout()
        ssl_context = self._get_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(timeout=self._timeout, connector=connector)

        # Инициализируем базовый класс
        # Используем api_url как base_url для базового класса
        super().__init__(
            base_url=config.api_url,
            session=self._session,
            service_name="gigachat",
            default_timeout=config.prompt_timeout.to_client_timeout(),
        )

        # Настройка SSL
        # Примечание: urllib3 используется только для отключения предупреждений при verify_ssl=False.
        # В aiohttp мы передаём verify_ssl напрямую в TCPConnector, поэтому urllib3 не нужен для async-запросов.
        # Но оставляем логирование для консистентности с синхронным клиентом.
        if self._verify_ssl is False:
            logger.warning("⚠️ Проверка SSL сертификатов для GigaChat отключена! Это снижает безопасность.")
        elif isinstance(self._verify_ssl, str):
            from pathlib import Path

            cert_path = Path(self._verify_ssl)
            if cert_path.exists():
                logger.info(f"✅ Используется сертификат для GigaChat: {self._verify_ssl}")
            else:
                logger.warning(f"⚠️ Файл сертификата не найден: {self._verify_ssl}. Проверка SSL может не работать.")

        logger.info("GigaChatTextClient инициализирован")

    # ------------------------------------------------------------------ #
    # Публичный интерфейс ITextToTextClient                             #
    # ------------------------------------------------------------------ #

    async def generate(self, prompt: str, user_id: str | None = None) -> str:
        """Генерирует промпт для Kandinsky через GigaChat API.

        Выполняет запрос к GigaChat API для генерации промпта для генерации изображения
        Wednesday Frog. Использует системное сообщение и пользовательский запрос из
        конфигурации.

        Args:
            prompt: Высокоуровневое описание задачи (для логов, не используется в запросе).
            user_id: Идентификатор пользователя для логирования.

        Returns:
            Сгенерированный промпт.

        Raises:
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="gigachat_generate", user_id=user_id)
        bound.info("Запрос генерации промпта через GigaChat API")

        access_token = await self._get_access_token()

        # Получаем текущую модель из хранилища или используем дефолтную
        current_model = await self._get_current_model()

        payload = {
            "model": current_model,
            "messages": [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": USER_MESSAGE},
            ],
            "max_tokens": MAX_TOKENS_DEFAULT,
            "temperature": 0.9,
            "top_p": 0.95,
            "n": 1,
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        bound.debug("Отправка запроса к GigaChat API для генерации промпта")
        # api_url уже полный URL, передаем его как endpoint
        response = await self._post(
            endpoint=self._api_url,
            method_name="generate",
            headers=headers,
            json=payload,
        )

        async with response:
            result_json = await self._parse_json_response(response)
            completion_response = GigaChatCompletionResponse.model_validate(result_json)
            if not completion_response.choices or not completion_response.choices[0]:
                bound.error("Ответ GigaChat API не содержит choices")
                raise APIError(
                    "Ответ GigaChat API не содержит choices",
                )

            generated_prompt = completion_response.choices[0].message.content.strip()
            generated_prompt = self._clean_prompt(generated_prompt)

            bound.info(f"Промпт успешно сгенерирован ({len(generated_prompt)} символов)")

            return generated_prompt

    @map_client_errors(event_name="gigachat_check_status", service_name="gigachat")
    async def check_api_status(self) -> APIStatusResult:  # type: ignore[override]
        """Проверяет статус GigaChat API без траты токенов (dry-run).

        Выполняет проверку доступности API и валидности ключа авторизации через
        попытку получения access token.

        Returns:
            APIStatusResult с информацией о статусе API.

        Raises:
            ValueError: Если API ключи не сконфигурированы.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="gigachat_check_status")
        bound.info("Проверка статуса GigaChat API")

        token = await self._get_access_token()
        if token:
            bound.info("✅ API доступен, ключ валиден")
            # Получаем текущую модель для включения в результат
            current_model = await self._get_current_model()
            return APIStatusResult.success(
                message="✅ API доступен, ключ валиден",
                models=[],  # GigaChat не возвращает список моделей в check_api_status
                current_model_id=None,
                current_model_name=current_model,
            )
        else:
            bound.warning("❌ Не удалось получить токен доступа")
            raise AuthenticationError(
                "Не удалось получить токен доступа GigaChat",
            )

    @map_client_errors(event_name="gigachat_get_models", service_name="gigachat")
    async def get_available_models(self, save_models: bool = True) -> list[str]:  # type: ignore[override]
        """Возвращает список доступных моделей GigaChat через API.

        Выполняет запрос к API для получения списка доступных моделей GigaChat.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять полученный список
                в хранилище для последующего использования.

        Returns:
            Список доступных моделей.

        Raises:
            ValueError: Если API ключи не сконфигурированы.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="gigachat_get_models", save_models=save_models)
        bound.info("Запрос списка моделей GigaChat")

        access_token = await self._get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        bound.debug("Отправка запроса к GigaChat API для получения списка моделей")
        timeout = self._config.models_timeout.to_client_timeout()
        # models_url может быть полным URL или относительным путем
        response = await self._get(
            endpoint=self._models_url,
            method_name="get_available_models",
            headers=headers,
            timeout=timeout,
        )

        async with response:
            data_json = await self._parse_json_response(response)
            models_list: list[str] = []

            # GigaChat может вернуть dict или list
            if isinstance(data_json, list):
                # Прямой список моделей (может быть list[dict] или list[str])
                models_parsed: list[GigaChatModelInfo] = []
                for item in data_json:
                    if isinstance(item, dict):
                        models_parsed.append(GigaChatModelInfo.model_validate(item))
                    elif isinstance(item, str):
                        models_parsed.append(GigaChatModelInfo(id=item, name=item, model=None))
                for model in models_parsed:
                    model_name = model.get_model_name()
                    if model_name:
                        models_list.append(model_name)
            elif isinstance(data_json, dict):
                # Dict с data/models
                models_response = GigaChatModelsListResponse.model_validate(data_json)
                models_list_parsed = models_response.get_models_list()
                for model in models_list_parsed:
                    model_name = model.get_model_name()
                    if model_name:
                        models_list.append(model_name)
            else:
                bound.error(f"Неожиданный формат ответа от API моделей: {type(data_json)}")
                raise APIError(
                    f"Неожиданный формат ответа от GigaChat API: {type(data_json)}",
                )

            if models_list:
                bound.info(f"Получен список из {len(models_list)} моделей GigaChat через API")
                if save_models:
                    # Сохраняем список моделей в async-хранилище
                    # Пока не сохраняем, так как это бизнес-логика
                    # В будущем можно добавить сохранение списка моделей
                    pass

                return models_list
            else:
                bound.warning("API вернул пустой список моделей")
                raise APIError(
                    "GigaChat API вернул пустой список моделей",
                )

    @map_client_errors(event_name="gigachat_set_model", service_name="gigachat")
    async def set_model(self, model_name: str) -> SetModelResult:  # type: ignore[override]
        """Выбирает модель GigaChat.

        Проверяет доступность указанной модели. НЕ сохраняет модель в хранилище -
        это ответственность app-слоя. Возвращает информацию о выбранной модели.

        Args:
            model_name: Название модели для установки.

        Returns:
            SetModelResult с информацией о выбранной модели (model_name).

        Raises:
            ValueError: Если модель не найдена.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        bound = logger.bind(event="gigachat_set_model", model_name=model_name)
        bound.info("Выбор модели GigaChat")

        available_models = await self.get_available_models(save_models=False)
        if model_name in available_models:
            msg = f"✅ Модель GigaChat выбрана: {model_name}"
            bound.info(msg)
            return SetModelResult.ok(msg, model_name=model_name)
        else:
            msg = f"❌ Модель '{model_name}' не найдена в списке доступных"
            bound.warning(msg)
            raise ValueError(msg)

    # ------------------------------------------------------------------ #
    # Приватные методы                                                   #
    # ------------------------------------------------------------------ #
    #
    # ШАБЛОНЫ ДЛЯ ДОБАВЛЕНИЯ НОВЫХ МЕТОДОВ:
    #
    # 1. Простой GET запрос с JSON:
    #    async def method_name(self, param: str) -> dict[str, Any]:
    #        return await self._get_json(
    #            endpoint=f"api/v1/endpoint/{param}",
    #            method_name="method_name",
    #            headers={"Authorization": f"Bearer {await self._get_access_token()}"},
    #        )
    #
    # 2. GET с кастомной обработкой (Pydantic валидация):
    #    async def method_name(self, param: str) -> ModelType:
    #        response = await self._get(
    #            endpoint=f"api/v1/endpoint/{param}",
    #            method_name="method_name",
    #            headers={"Authorization": f"Bearer {await self._get_access_token()}"},
    #        )
    #        async with response:
    #            data = await self._parse_json_response(response)
    #            return ModelType.model_validate(data)
    #
    # 3. POST с JSON:
    #    async def method_name(self, data: dict[str, Any]) -> dict[str, Any]:
    #        return await self._post_json(
    #            endpoint="api/v1/endpoint",
    #            method_name="method_name",
    #            headers={"Authorization": f"Bearer {await self._get_access_token()}"},
    #            json=data,
    #        )
    #
    # 4. POST с FormData:
    #    async def method_name(self, file_data: bytes) -> dict[str, Any]:
    #        form_data = aiohttp.FormData()
    #        form_data.add_field("file", file_data, filename="file.png")
    #        response = await self._post(
    #            endpoint="api/v1/upload",
    #            method_name="method_name",
    #            headers={"Authorization": f"Bearer {await self._get_access_token()}"},
    #            data=form_data,
    #        )
    #        async with response:
    #            return await self._parse_json_response(response)
    #

    async def aclose(self) -> None:
        """Явно закрывает внутренний aiohttp.ClientSession.

        Закрывает HTTP-сессию и освобождает все связанные ресурсы. Рекомендуется
        вызывать при завершении приложения, чтобы избежать предупреждений о
        незакрытых соединениях.

        Note:
            Ошибки при закрытии логируются, но не пробрасываются наружу.
        """
        try:
            await self._session.close()
        except Exception as exc:  # pragma: no cover - защитное логирование
            logger.warning(f"Не удалось корректно закрыть GigaChatTextClient session: {exc!s}")

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

    def _get_ssl_context(self) -> bool | ssl.SSLContext:
        """Преобразует verify_ssl в формат, подходящий для aiohttp.TCPConnector.

        Returns:
            bool для отключения/включения проверки SSL или SSLContext для кастомного сертификата.
        """
        if isinstance(self._verify_ssl, bool):
            return self._verify_ssl
        elif isinstance(self._verify_ssl, str):
            # Если указан путь к сертификату, создаём SSLContext
            from pathlib import Path

            cert_path = Path(self._verify_ssl)
            if cert_path.exists():
                ssl_context = ssl.create_default_context(cafile=str(cert_path))
                return ssl_context
            else:
                # Если файл не найден, используем стандартную проверку
                return True
        else:
            # По умолчанию включаем проверку SSL
            return True

    async def _get_access_token(self) -> str:
        """Получает access token для работы с API, кэшируя до истечения срока действия.

        Returns:
            Access token.

        Raises:
            ValueError: Если authorization_key не установлен.
            AuthenticationError: Если API ключи неверны или доступ запрещён (401, 403).
            RateLimitError: Если превышен лимит запросов (429).
            NetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            APIError: При других ошибках API (4xx, 5xx).
        """
        # Сначала быстрая проверка без блокировки.
        if self._access_token and self._token_expiry_time and time.time() < self._token_expiry_time:
            return self._access_token

        # Гарантируем, что только один concurrent‑поток ходит за новым токеном.
        async with self._token_lock:
            # Повторная проверка внутри lock на случай гонки.
            if self._access_token and self._token_expiry_time and time.time() < self._token_expiry_time:
                return self._access_token

            bound = logger.bind(event="gigachat_get_token")
            bound.info("Запрос нового токена доступа GigaChat")

            if not self._authorization_key:
                bound.error("GIGACHAT_AUTHORIZATION_KEY не установлен в конфигурации")
                raise ValueError("GIGACHAT_AUTHORIZATION_KEY не установлен в конфигурации")

            # Логируем диагностическую информацию (без вывода полного ключа)
            key_length = len(self._authorization_key)
            key_preview = (
                self._authorization_key[:AUTH_KEY_PREVIEW_LENGTH] + "..."
                if key_length > AUTH_KEY_PREVIEW_LENGTH
                else "*" * min(key_length, AUTH_KEY_PREVIEW_LENGTH)
            )
            bound.debug(f"Используется authorization_key длиной {key_length} символов: {key_preview}")

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {self._authorization_key}",
            }

            payload = {"scope": self._scope}
            timeout = self._config.token_timeout.to_client_timeout()

            try:
                # auth_url может быть полным URL или относительным путем
                response = await self._post(
                    endpoint=self._auth_url,
                    method_name="get_access_token",
                    headers=headers,
                    data=payload,
                    timeout=timeout,
                )

                async with response:
                    token_data_json = await self._parse_json_response(response)
                    try:
                        token_response = GigaChatTokenResponse.model_validate(token_data_json)
                        self._access_token = token_response.access_token
                        expires_in = token_response.expires_in
                        self._token_expiry_time = time.time() + expires_in - TOKEN_EXPIRY_BUFFER_SECONDS

                        bound.info("Успешно получен access token для GigaChat")
                        return self._access_token
                    except ValidationError as e:
                        bound.bind(
                            error=str(e),
                            data_sample=str(token_data_json)[:200],
                        ).error("Ошибка валидации ответа GigaChat API при получении токена")
                        raise APIError(
                            f"Ошибка валидации ответа GigaChat API при получении токена: {e}",
                            original_error=e,
                        ) from e
            except (AuthenticationError, RateLimitError, NetworkError, APIError):
                raise
            except Exception as exc:
                bound.error(f"Неожиданная ошибка при получении токена GigaChat: {exc}", exc_info=True)
                raise APIError(
                    f"Неожиданная ошибка при получении токена GigaChat: {exc}",
                    original_error=exc,
                ) from exc

    async def _get_current_model(self) -> str:
        """Получает текущую модель из хранилища или использует дефолтную.

        Returns:
            Название текущей модели.
        """
        try:
            stored_model = await self._models_repo.get_gigachat_model()
            if stored_model:
                return stored_model
        except Exception:
            # Если не удалось получить из хранилища, используем дефолтную
            pass

        return self._model

    @staticmethod
    def _clean_prompt(prompt: str) -> str:
        """Очищает промпт от лишних символов, форматирования и маркеров.

        Args:
            prompt: Исходный промпт.

        Returns:
            Очищенный промпт.
        """
        # Удаляем маркеры типа "```" если есть
        prompt = prompt.replace("```", "")

        # Удаляем префиксы типа "Промпт:" если есть
        prompt = prompt.replace("Prompt:", "").replace("prompt:", "").replace("Промпт:", "")

        # Удаляем кавычки в начале и конце если есть
        prompt = prompt.strip("\"'")

        # Удаляем лишние пробелы
        prompt = " ".join(prompt.split())

        return prompt.strip()
