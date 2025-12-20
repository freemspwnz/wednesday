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
from typing import Self

import aiohttp
from loguru import logger

from services.protocols import IModelsRepo, ITextToTextClient
from utils.config import GigaChatConfig
from utils.models_repo import ModelsRepo
from utils.retry import retry_critical, retry_standard

HTTP_STATUS_OK = 200
TIMEOUT_TOKEN_SECONDS = 60
TIMEOUT_PROMPT_SECONDS = 60
TIMEOUT_MODELS_SECONDS = 30
TOKEN_EXPIRY_BUFFER_SECONDS = 300
DEFAULT_EXPIRES_IN_SECONDS = 1800
MAX_TOKENS_DEFAULT = 300
MAX_ERROR_TEXT_LENGTH = 100
AUTH_KEY_PREVIEW_LENGTH = 10

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


class GigaChatTextClient(ITextToTextClient):
    """HTTP‑клиент GigaChat, реализующий интерфейс `ITextToTextClient`.

    Архитектурно клиент отвечает только за:

    - корректное обращение к HTTP‑эндпоинтам GigaChat;
    - авторизацию через OAuth2 и кэширование токенов;
    - выбор модели и генерацию текста;
    - обработку сетевых ошибок и таймаутов.

    Любые бизнес‑аспекты (сохранение промптов в файлы, кеш, Prometheus)
    реализуются на уровне сервисов, использующих этот клиент.
    """

    def __init__(
        self,
        config: GigaChatConfig,
        models_repo: IModelsRepo | None = None,
    ) -> None:
        """Инициализация клиента GigaChat.

        Args:
            config: Конфигурация GigaChat клиента (обязательна).
            models_repo: Репозиторий моделей для сохранения/получения настроек моделей.
                Если не передан, создается новый экземпляр ModelsRepo при необходимости.
        """
        self._auth_url: str = config.auth_url
        self._api_url: str = config.api_url
        self._authorization_key: str = config.authorization_key
        self._scope: str = config.scope
        self._verify_ssl: bool | str = config.verify_ssl
        self._model: str = config.model
        self._models_repo: IModelsRepo | None = models_repo

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
        self._timeout = aiohttp.ClientTimeout(total=TIMEOUT_PROMPT_SECONDS, connect=10, sock_read=30)
        ssl_context = self._get_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(timeout=self._timeout, connector=connector)

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

    async def generate(self, prompt: str, user_id: str | None = None) -> str | None:
        """Генерирует промпт для Kandinsky через GigaChat API.

        Выполняет запрос к GigaChat API для генерации промпта для генерации изображения
        Wednesday Frog. Использует системное сообщение и пользовательский запрос из
        конфигурации.

        Args:
            prompt: Высокоуровневое описание задачи (для логов, не используется в запросе).
            user_id: Идентификатор пользователя для логирования (опционально).

        Returns:
            Сгенерированный промпт в виде строки или None при ошибке.

        Raises:
            TimeoutError: При таймауте запроса к API.
            aiohttp.ClientConnectorError: При ошибке подключения к API.
            aiohttp.ClientError: При других ошибках HTTP-клиента.
        """
        bound = logger.bind(event="gigachat_generate", user_id=user_id)
        bound.info("Запрос генерации промпта через GigaChat API")

        access_token = await self._get_access_token()
        if not access_token:
            bound.error("Не удалось получить access token для генерации промпта")
            return None

        try:
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

            @retry_standard(service_name="gigachat", method_name="generate")
            async def _post_generate() -> aiohttp.ClientResponse:
                return await self._session.post(self._api_url, headers=headers, json=payload)

            bound.debug("Отправка запроса к GigaChat API для генерации промпта")
            async with await _post_generate() as response:
                if response.status == HTTP_STATUS_OK:
                    result = await response.json()
                    generated_prompt = result["choices"][0]["message"]["content"].strip()
                    generated_prompt = self._clean_prompt(generated_prompt)

                    bound.info(f"Промпт успешно сгенерирован ({len(generated_prompt)} символов)")

                    return generated_prompt
                else:
                    error_text = (await response.text())[:MAX_ERROR_TEXT_LENGTH]
                    bound.error(
                        f"Ошибка GigaChat API при генерации промпта: {response.status} - {error_text}",
                    )
                    return None
        except TimeoutError:
            bound.error(f"Таймаут при генерации промпта через GigaChat ({TIMEOUT_PROMPT_SECONDS} секунд)")
            return None
        except aiohttp.ClientConnectorError as e:
            bound.error(f"Ошибка подключения к GigaChat API при генерации промпта: {e}")
            return None
        except aiohttp.ClientError as e:
            bound.error(f"Ошибка клиента при генерации промпта: {e}")
            return None
        except Exception as e:
            bound.error(f"Неожиданная ошибка при генерации промпта: {e}", exc_info=True)
            return None

    async def check_api_status(self) -> tuple[bool, str]:
        """Проверяет статус GigaChat API без траты токенов (dry-run).

        Выполняет проверку доступности API и валидности ключа авторизации через
        попытку получения access token.

        Returns:
            Кортеж, содержащий:
            - успех_проверки: True если API доступен и ключ валиден.
            - сообщение_о_статусе: Человекочитаемое сообщение о статусе.

        Raises:
            Exception: При ошибке проверки статуса.
        """
        bound = logger.bind(event="gigachat_check_status")
        bound.info("Проверка статуса GigaChat API")

        try:
            token = await self._get_access_token()
            if token:
                bound.info("✅ API доступен, ключ валиден")
                return True, "✅ API доступен, ключ валиден"
            else:
                bound.warning("❌ Не удалось получить токен доступа")
                return False, "❌ Не удалось получить токен доступа"
        except Exception as e:
            error_msg = f"❌ Ошибка проверки: {str(e)[:50]}"
            bound.error(f"Ошибка при проверке статуса: {e}", exc_info=True)
            return False, error_msg

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Возвращает список доступных моделей GigaChat через API.

        Выполняет запрос к API для получения списка доступных моделей GigaChat.

        Args:
            save_models: Сохранять ли полученный список в хранилище (по умолчанию True).

        Returns:
            Список доступных моделей. В случае ошибки возвращает fallback-список
            стандартных моделей GigaChat.

        Note:
            При любой ошибке (таймаут, ошибка подключения и т.д.) возвращается
            fallback-список стандартных моделей для обеспечения отказоустойчивости.
        """
        bound = logger.bind(event="gigachat_get_models", save_models=save_models)
        bound.info("Запрос списка моделей GigaChat")

        access_token = await self._get_access_token()
        if not access_token:
            bound.warning("Не удалось получить токен для запроса списка моделей, используем fallback")
            return FALLBACK_MODELS.copy()

        try:
            models_url = "https://gigachat.devices.sberbank.ru/api/v1/models"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            @retry_standard(service_name="gigachat", method_name="get_available_models")
            async def _get_models() -> aiohttp.ClientResponse:
                timeout = aiohttp.ClientTimeout(total=TIMEOUT_MODELS_SECONDS, connect=10, sock_read=20)
                return await self._session.get(models_url, headers=headers, timeout=timeout)

            bound.debug("Отправка запроса к GigaChat API для получения списка моделей")
            async with await _get_models() as response:
                if response.status == HTTP_STATUS_OK:
                    data = await response.json()

                    # API может вернуть данные в разных форматах
                    if isinstance(data, dict):
                        models_data = data.get("data", data.get("models", []))
                    elif isinstance(data, list):
                        models_data = data
                    else:
                        bound.warning(f"Неожиданный формат ответа от API моделей: {type(data)}")
                        return FALLBACK_MODELS.copy()

                    models_list: list[str] = []
                    if models_data is None:
                        return FALLBACK_MODELS.copy()

                    for model in models_data:
                        if isinstance(model, dict):
                            model_name = model.get("id") or model.get("name") or model.get("model")
                        elif isinstance(model, str):
                            model_name = model
                        else:
                            continue

                        if model_name:
                            models_list.append(model_name)

                    if models_list:
                        bound.info(f"Получен список из {len(models_list)} моделей GigaChat через API")
                        if save_models:
                            # Сохраняем список моделей в async-хранилище
                            # Пока не сохраняем, так как это бизнес-логика
                            # В будущем можно добавить сохранение списка моделей
                            pass

                        return models_list
                    else:
                        bound.warning("API вернул пустой список моделей, используем fallback")
                        return FALLBACK_MODELS.copy()
                else:
                    error_text = (await response.text())[:MAX_ERROR_TEXT_LENGTH]
                    bound.warning(
                        f"Ошибка при запросе списка моделей: {response.status} - {error_text}, используем fallback",
                    )
                    return FALLBACK_MODELS.copy()

        except TimeoutError:
            bound.warning(
                f"Таймаут при запросе списка моделей GigaChat ({TIMEOUT_MODELS_SECONDS} секунд), используем fallback",
            )
            return FALLBACK_MODELS.copy()
        except aiohttp.ClientConnectorError as e:
            bound.warning(f"Ошибка подключения при запросе списка моделей GigaChat: {e}, используем fallback")
            return FALLBACK_MODELS.copy()
        except aiohttp.ClientError as e:
            bound.warning(f"Ошибка запроса при получении списка моделей GigaChat: {e}, используем fallback")
            return FALLBACK_MODELS.copy()
        except Exception as e:
            bound.warning(f"Неожиданная ошибка при получении списка моделей: {e}, используем fallback", exc_info=True)
            return FALLBACK_MODELS.copy()

    async def set_model(self, model_name: str) -> tuple[bool, str]:
        """Устанавливает текущую модель GigaChat.

        Проверяет доступность указанной модели и сохраняет её в хранилище для
        использования в последующих запросах.

        Args:
            model_name: Название модели для установки.

        Returns:
            Кортеж, содержащий:
            - успех: True если модель установлена успешно.
            - сообщение: Человекочитаемое сообщение о результате.

        Raises:
            Exception: При ошибке установки модели (например, ошибка доступа к хранилищу).
        """
        bound = logger.bind(event="gigachat_set_model", model_name=model_name)
        bound.info("Установка модели GigaChat")

        try:
            available_models = await self.get_available_models(save_models=False)
            if model_name in available_models:
                # Сохраняем модель в async-хранилище
                models_store = self._models_repo if self._models_repo is not None else ModelsRepo()
                await models_store.set_gigachat_model(model_name)
                self._model = model_name

                bound.info(f"✅ Модель GigaChat установлена: {model_name}")
                return True, f"✅ Модель GigaChat установлена: {model_name}"
            else:
                bound.warning(f"Попытка установить несуществующую модель: {model_name}")
                return False, f"❌ Модель '{model_name}' не найдена в списке доступных"
        except Exception as e:
            error_msg = f"❌ Ошибка при установке модели: {str(e)[:50]}"
            bound.error(f"Ошибка при установке модели: {e}", exc_info=True)
            return False, error_msg

    # ------------------------------------------------------------------ #
    # Приватные методы                                                   #
    # ------------------------------------------------------------------ #

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

    async def _get_access_token(self) -> str | None:
        """Получает access token для работы с API, кэшируя до истечения срока действия.

        Returns:
            Access token или None при ошибке.
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
                return None

            # Логируем диагностическую информацию (без вывода полного ключа)
            key_length = len(self._authorization_key)
            key_preview = (
                self._authorization_key[:AUTH_KEY_PREVIEW_LENGTH] + "..."
                if key_length > AUTH_KEY_PREVIEW_LENGTH
                else "*" * min(key_length, AUTH_KEY_PREVIEW_LENGTH)
            )
            bound.debug(f"Используется authorization_key длиной {key_length} символов: {key_preview}")

            @retry_critical(service_name="gigachat", method_name="get_access_token")
            async def _fetch_token() -> aiohttp.ClientResponse:
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": str(uuid.uuid4()),
                    "Authorization": f"Basic {self._authorization_key}",
                }

                payload = {"scope": self._scope}

                timeout = aiohttp.ClientTimeout(total=TIMEOUT_TOKEN_SECONDS, connect=10, sock_read=30)
                return await self._session.post(self._auth_url, headers=headers, data=payload, timeout=timeout)

            try:
                async with await _fetch_token() as response:
                    if response.status == HTTP_STATUS_OK:
                        token_data = await response.json()
                        self._access_token = token_data["access_token"]
                        expires_in = token_data.get("expires_in", DEFAULT_EXPIRES_IN_SECONDS)
                        self._token_expiry_time = time.time() + expires_in - TOKEN_EXPIRY_BUFFER_SECONDS

                        bound.info("Успешно получен access token для GigaChat")
                        return self._access_token
                    else:
                        error_text = (await response.text())[:MAX_ERROR_TEXT_LENGTH]
                        bound.error(
                            f"Ошибка аутентификации GigaChat: {response.status} - {error_text}. "
                            "Проверьте, что GIGACHAT_AUTHORIZATION_KEY правильно настроен",
                        )
                        return None
            except TimeoutError:
                bound.error(f"Таймаут при получении токена GigaChat ({TIMEOUT_TOKEN_SECONDS} секунд)")
                return None
            except aiohttp.ClientConnectorError as e:
                bound.error(f"Ошибка подключения к GigaChat API при получении токена: {e}")
                return None
            except aiohttp.ClientError as e:
                bound.error(f"Ошибка клиента при получении токена: {e}")
                return None
            except Exception as e:
                bound.error(f"Неожиданная ошибка при получении токена GigaChat: {e}", exc_info=True)
                return None

    async def _get_current_model(self) -> str:
        """Получает текущую модель из хранилища или использует дефолтную.

        Returns:
            Название текущей модели.
        """
        try:
            models_store = self._models_repo if self._models_repo is not None else ModelsRepo()
            stored_model = await models_store.get_gigachat_model()
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
