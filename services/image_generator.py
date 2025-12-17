"""
Сервис для генерации изображений жабы.

DEPRECATED: Этот класс является временной обёрткой над новой архитектурой сервисов.
Вся логика генерации перенесена в `ImageService` и связанные сервисы.
Этот класс будет удалён в спринте 5.

`ImageGenerator` теперь является тонкой обёрткой над `ImageService`, сохраняя
публичный интерфейс для обратной совместимости.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from services.application.image_service import ImageService
from services.application.prompt_service import PromptService
from services.clients import ITextToImageClient, ITextToTextClient
from services.clients.factory import create_image_client, create_text_client
from services.clients.image_client_container import ImageClientContainer
from services.clients.kandinsky import KandinskyClient
from services.domain.image_generation import ImageGenerationService
from services.domain.prompt_generation import PromptGenerationService
from services.infrastructure.cache.image_cache import ImageCacheService
from services.infrastructure.cache.prompt_cache import PromptCache
from services.infrastructure.metrics.metrics_recorder import MetricsRecorder
from services.infrastructure.rate_limiting import CircuitBreaker
from services.infrastructure.rate_limiting.circuit_breaker import CircuitBreakerService
from services.infrastructure.storage.image_storage import ImageStorageService
from services.infrastructure.storage.prompt_storage import PromptStorageService
from services.prompt_generator import PromptStorage
from utils.config import ImageConfig, config
from utils.logger import get_logger, log_all_methods
from utils.metrics import Metrics
from utils.paths import FROGS_DIR
from utils.prompts_store import PromptsStore

if TYPE_CHECKING:
    pass

# Константы для магических чисел
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 300  # 5 минут
MAX_FILES_DEFAULT = 30


@log_all_methods()
class ImageGenerator:
    """
    Класс для генерации изображений жабы с помощью Kandinsky API.

    Обеспечивает:
    - Асинхронную генерацию изображений
    - Обработку ошибок и повторные попытки
    - Сохранение изображений в память
    - Случайный выбор подписей
    """

    def __init__(
        self,
        image_client: ITextToImageClient | None = None,
        text_client: ITextToTextClient | None = None,
    ) -> None:
        """Инициализация генератора изображений.

        В конструкторе мы больше не создаём HTTP‑клиенты напрямую. Вместо этого:

        - принимаем абстрактные интерфейсы `ITextToImageClient` и `ITextToTextClient`;
        - при отсутствии явных значений используем фабрики `create_image_client`
          и `create_text_client`, которые выбирают реализации по ENV‑переменным
          (`IMAGE_MODEL_BACKEND`, `TEXT_MODEL_BACKEND`);
        - оставляем весь сетевой код внутри клиентов, а не в `ImageGenerator`.

        Такой подход упрощает замену моделей (другой провайдер, on‑prem LLM)
        и делает юнит‑тесты чище: можно подставлять структурные моки вместо
        реальных HTTP‑клиентов.
        """

        self.logger = get_logger(__name__)
        self.max_retries: int = config.max_retries

        # DI: клиенты генерации изображений и текста.
        # Для текста по умолчанию используется singleton‑контейнер
        # `TextClientContainer`, возвращаемый `create_text_client()`. Это
        # позволяет в будущем безопасно менять реализацию LLM‑клиента
        # (например, GigaChat -> другой провайдер) в рантайме без рестарта
        # бота: все сервисы держат ссылку на контейнер, а не на конкретный
        # `GigaChatTextClient`.
        # Для изображений аналогично используется singleton‑контейнер
        # `ImageClientContainer`, возвращаемый `create_image_client()`, что
        # позволяет безопасно менять TTI‑бэкенд в рантайме без рестарта бота.
        if image_client is None:
            # Используем контейнер из фабрики (singleton).
            self._image_client: ITextToImageClient = create_image_client()
        elif isinstance(image_client, ImageClientContainer):
            # Уже передан контейнер - используем его напрямую.
            self._image_client = image_client
        else:
            # Передан прямой клиент (например, в тестах или для обратной совместимости).
            # Оборачиваем его в контейнер для поддержки замены в runtime.
            from services.clients.image_client_container import get_image_client_container

            container = get_image_client_container()
            container.set_initial_client(image_client)
            self._image_client = container

        self._text_client: ITextToTextClient | None = text_client or create_text_client()

        # Для обратной совместимости с тестами сохраняем ссылку на KandinskyClient, если он используется.
        # В новой архитектуре все методы доступны через image_client (контейнер).
        underlying_client = (
            self._image_client.get_client()
            if isinstance(self._image_client, ImageClientContainer)
            else self._image_client
        )
        self._kandinsky_client: KandinskyClient | None = (
            underlying_client if isinstance(underlying_client, KandinskyClient) else None
        )

        # Circuit breaker для API.
        # Исторически счётчики хранились в памяти, что сбрасывало состояние при рестарте.
        # Теперь используем Redis‑базированный CircuitBreaker, чтобы:
        # - разделять счётчики между воркерами/процессами;
        # - сохранять окно ошибок даже при перезапуске приложения.
        #
        # Локальные поля оставлены только для обратной совместимости логов
        # и могут быть удалены в будущих версиях.
        self.circuit_breaker_failures: int = 0
        self.circuit_breaker_threshold: int = CIRCUIT_BREAKER_THRESHOLD
        self.circuit_breaker_cooldown: int = CIRCUIT_BREAKER_COOLDOWN_SECONDS
        self.circuit_breaker_open_until: float | None = None
        self._circuit_breaker = CircuitBreaker(
            key="cb:kandinsky_api",
            threshold=CIRCUIT_BREAKER_THRESHOLD,
            window=CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )

        # Промпт для генерации жабы (fallback)
        self.frog_prompt: list[str] = ImageConfig.FROG_PROMPTS
        self.style: list[str] = ImageConfig.STYLES

        # Размеры изображения
        self.width: int = ImageConfig.WIDTH
        self.height: int = ImageConfig.HEIGHT

        # Подписи для изображений
        self.captions: list[str] = ImageConfig.CAPTIONS

        # Файловое хранилище промптов:
        # - исторический fallback, использовался до появления Postgres‑хранилища;
        # - сейчас основной источник истины для промптов — таблица `prompts`,
        #   а файлы используются только как дополнительный backup.
        self.prompt_storage: PromptStorage = PromptStorage()

        # Текстовый клиент теперь полностью инкапсулирует HTTP-логику и реализует
        # все методы интерфейса ITextToTextClient (generate, check_api_status,
        # get_available_models, set_model). Обработчики должны использовать
        # self.text_client напрямую вместо устаревшего gigachat_client.

        # Создаём новую архитектуру сервисов для использования в generate_frog_image()
        self._image_service = self._create_image_service()

        self.logger.info("Генератор изображений инициализирован")

    def _create_image_service(self) -> ImageService:
        """Создаёт ImageService с использованием текущих клиентов.

        Returns:
            Настроенный экземпляр ImageService.
        """
        # Доменные сервисы
        image_generation_service = ImageGenerationService(self._image_client)
        prompt_generation_service = PromptGenerationService(self._text_client)

        # Инфраструктурные сервисы
        image_cache = ImageCacheService()
        image_storage = ImageStorageService()
        prompt_cache = PromptCache()
        prompt_storage = PromptStorageService()
        circuit_breaker = CircuitBreakerService(
            key="cb:kandinsky_api",
            threshold=CIRCUIT_BREAKER_THRESHOLD,
            window=CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )
        metrics_recorder = MetricsRecorder()

        # Application сервисы
        prompt_service = PromptService(
            prompt_generation_service=prompt_generation_service,
            prompt_cache=prompt_cache,
            prompt_storage=prompt_storage,
        )

        image_service = ImageService(
            image_generation_service=image_generation_service,
            prompt_service=prompt_service,
            image_cache=image_cache,
            image_storage=image_storage,
            circuit_breaker=circuit_breaker,
            metrics=metrics_recorder,
            max_retries=self.max_retries,
        )

        return image_service

    @property
    def image_client(self) -> ITextToImageClient:
        """Возвращает клиент генерации изображений.

        Returns:
            Экземпляр клиента, реализующего интерфейс ITextToImageClient.
        """
        return self._image_client

    @property
    def text_client(self) -> ITextToTextClient | None:
        """Возвращает клиент генерации текста.

        Returns:
            Экземпляр клиента, реализующего интерфейс ITextToTextClient, или None
            если текстовый клиент не настроен.
        """
        return self._text_client

    async def generate_frog_image(
        self,
        user_id: int | None = None,
        metrics: Metrics | None = None,
    ) -> tuple[bytes, str] | None:
        """Генерирует изображение жабы с помощью Kandinsky API.

        DEPRECATED: Этот метод теперь является обёрткой над ImageService.
        Параметр metrics игнорируется, так как метрики записываются через MetricsRecorder
        внутри ImageService.

        Args:
            user_id: Идентификатор пользователя для логирования и метрик (опционально).
            metrics: Экземпляр Metrics (игнорируется, оставлен для обратной совместимости).

        Returns:
            Кортеж (изображение в байтах, случайная подпись) или None при ошибке.

        Note:
            Вся логика генерации теперь выполняется через ImageService.
        """
        # Используем новый ImageService для генерации
        return await self._image_service.generate_frog_image(user_id=user_id)

    async def _generate_image(self, prompt: str) -> bytes | None:  # pragma: no cover
        """Устаревший helper прямого обращения к Kandinsky API.

        Логика генерации целиком вынесена в `KandinskyClient`, этот метод
        сохранён только для обратной совместимости и больше не используется.
        """
        self.logger.warning("ImageGenerator._generate_image устарел и больше не используется")
        _ = prompt
        return None

    async def check_api_status(
        self,
        save_models: bool = True,
    ) -> tuple[bool, str, list[str], tuple[str | None, str | None]]:
        """Проверяет статус API и валидность ключа без генерации изображения (dry-run).

        DEPRECATED: Используйте напрямую `image_generator.image_client.check_api_status()`.
        Этот метод сохранён для обратной совместимости.

        Args:
            save_models: Флаг, указывающий, нужно ли сохранять список доступных моделей.

        Returns:
            Кортеж, содержащий:
            - успех_проверки: True если API доступен и ключ валиден.
            - сообщение_о_статусе: Человекочитаемое сообщение о статусе.
            - список_моделей: Список доступных моделей.
            - (текущий_pipeline_id, текущее_имя): ID и название текущей модели.
        """
        self.logger.warning(
            "ImageGenerator.check_api_status() устарел, используйте image_client.check_api_status() напрямую",
        )
        return await self._image_client.check_api_status(save_models=save_models)

    async def _start_generation(self, *_args: object, **_kwargs: object) -> str | None:  # pragma: no cover
        """Устаревший helper прямого запуска генерации на Kandinsky."""
        self.logger.warning("ImageGenerator._start_generation устарел и больше не используется")
        return None

    async def _wait_for_generation(self, *_args: object, **_kwargs: object) -> bytes | None:  # pragma: no cover
        """Устаревший helper ожидания завершения генерации на Kandinsky."""
        self.logger.warning("ImageGenerator._wait_for_generation устарел и больше не используется")
        return None

    async def _generate_prompt(self) -> str | None:
        """Генерирует промпт для Kandinsky через текстовый клиент или использует fallback.

        Выполняет генерацию промпта с использованием многоуровневой стратегии fallback:
        1. Попытка получить промпт из абстрактного `ITextToTextClient` (по умолчанию GigaChat).
        2. При любой ошибке/пустом ответе — берём случайный промпт из таблицы `prompts`.
        3. Если в БД нет данных — используем файловый fallback из `data/prompts/`.
        4. Если и файлов нет — вызывающий код использует статический fallback.

        Returns:
            Сгенерированный промпт в виде строки или None, если все источники недоступны.

        Note:
            При любом успешно выбранном промпте он регистрируется в таблице `prompts`
            (raw + normalized + hash), чтобы БД оставалась каноническим источником метаданных.
        """
        prompts_store = PromptsStore()
        prompt: str | None = None

        # 1. Пытаемся сгенерировать промпт через абстрактный текстовый клиент.
        if self._text_client is not None:
            try:
                candidate = await self._text_client.generate("prompt_for_kandinsky")
                if candidate:
                    prompt = candidate
                else:
                    self.logger.warning(
                        "Текстовый клиент вернул пустой промпт, пробуем использовать сохранённые промпты из БД",
                    )
            except Exception as e:
                # Любая ошибка клиента переводит нас на fallback.
                self.logger.error(
                    f"Ошибка при генерации промпта через текстовый клиент, используем fallback: {e}",
                    exc_info=True,
                )

        # 2. Fallback на сохранённые в БД промпты.
        if prompt is None:
            try:
                random_record = await prompts_store.get_random_prompt()
            except Exception as e:
                self.logger.error(
                    f"Ошибка при получении fallback-промпта из БД: {e}",
                    exc_info=True,
                )
                random_record = None

            if random_record is not None:
                self.logger.info(
                    "Используем fallback-промпт из таблицы prompts "
                    f"(id={random_record.id}, hash={random_record.prompt_hash})",
                )
                prompt = random_record.raw_text

        # 3. Файловый fallback: историческое хранилище `data/prompts/`.
        if prompt is None:
            try:
                file_prompt = self.prompt_storage.get_random_prompt()
            except Exception as e:  # на всякий случай не ломаем основную логику
                self.logger.error(
                    f"Ошибка при получении fallback-промпта из файлового хранилища: {e}",
                    exc_info=True,
                )
                file_prompt = None

            if file_prompt:
                self.logger.info("Используем fallback-промпт из сохранённых файлов data/prompts")
                prompt = file_prompt

        # 4. Если даже файлового fallback-а нет — вызывающий код перейдёт к статическому промпту.
        if prompt is None:
            self.logger.warning(
                "Fallback-промпт недоступен (ни БД, ни файлы). Будет использован статический fallback-промпт.",
            )
            return None

        # Регистрируем выбранный промпт в таблице `prompts`
        # (алгоритм нормализации и hash реализован в репозитории).
        try:
            record = await prompts_store.get_or_create_prompt(prompt)
            self.logger.info(
                f"Промпт зарегистрирован в БД для генерации: id={record.id}, hash={record.prompt_hash}",
            )
        except Exception as e:  # pragma: no cover - защитный фоллбек
            self.logger.error(f"Не удалось сохранить промпт в таблице prompts: {e}", exc_info=True)

        return prompt

    @staticmethod
    def _get_fallback_prompt() -> str:
        """Возвращает промпт из статического списка (fallback).

        Используется когда не удалось получить промпт через текстовый клиент
        или из базы данных. Выбирает случайный промпт и стиль из конфигурации.

        Returns:
            Промпт для генерации изображения в формате строки.
        """
        # Выбираем случайный промпт и стиль для разнообразия
        frog_prompt = random.choice(ImageConfig.FROG_PROMPTS)
        style = random.choice(ImageConfig.STYLES)

        # Формируем полный промпт
        return f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"

    def get_random_caption(self) -> str:
        """Возвращает случайную подпись для изображения.

        Выбирает случайную подпись из предопределённого списка подписей для
        изображений жабы.

        Returns:
            Случайная подпись из списка доступных подписей.
        """
        return random.choice(self.captions)

    async def _save_image_async(
        self,
        image_data: bytes,
        folder: Path | str = FROGS_DIR,
        prefix: str = "frog",
        max_files: int = MAX_FILES_DEFAULT,
    ) -> str:
        """Асинхронная обёртка над save_image_locally для использования в async‑коде.

        Выполняет синхронные файловые операции в отдельном потоке через
        loop.run_in_executor, чтобы не блокировать event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.save_image_locally(
                image_data=image_data,
                folder=folder,
                prefix=prefix,
                max_files=max_files,
            ),
        )

    def save_image_locally(
        self,
        image_data: bytes,
        folder: Path | str = FROGS_DIR,
        prefix: str = "frog",
        max_files: int = MAX_FILES_DEFAULT,
    ) -> str:
        """Сохраняет байты изображения на диск.

        Сохраняет изображение в указанную папку с временной меткой в имени файла.
        При достижении лимита max_files автоматически удаляет самые старые файлы.

        Args:
            image_data: Содержимое изображения в байтах.
            folder: Папка для сохранения (по умолчанию FROGS_DIR).
            prefix: Префикс имени файла (по умолчанию "frog").
            max_files: Максимальное количество файлов в папке (по умолчанию 30).

        Returns:
            Путь к сохраненному файлу или пустая строка при ошибке.

        Note:
            По умолчанию используется относительный путь `data/frogs`. Внутри
            Docker-контейнера при WORKDIR=/app это соответствует абсолютному пути
            /app/data/frogs, который примонтирован как volume.

        Raises:
            PermissionError: При отсутствии прав на запись в директорию.
            OSError: При ошибках файловой системы (недостаточно места и т.д.).
        """
        try:
            # Разрешаем путь через единый helper, чтобы обеспечить единообразное
            # поведение в контейнере и при локальном запуске.
            path = FROGS_DIR if folder == FROGS_DIR else Path(folder)
            path.mkdir(parents=True, exist_ok=True)

            # Сохраняем новый файл
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = path / f"{prefix}_{ts}.png"
            file_path.write_bytes(image_data)
            self.logger.info(f"Изображение сохранено: {file_path}")

            # Ограничим количество файлов в папке
            # Получаем все PNG файлы и сортируем по времени модификации (новейшие первые)
            try:
                all_files = list(path.glob("*.png"))

                if len(all_files) > max_files:
                    # Сортируем по времени модификации: новейшие файлы первыми
                    files_sorted = sorted(all_files, key=lambda p: p.stat().st_mtime, reverse=True)

                    # Удаляем самые старые файлы (начиная с индекса max_files)
                    files_to_delete = files_sorted[max_files:]
                    deleted_count = 0

                    for old_file in files_to_delete:
                        try:
                            # Не удаляем только что сохраненный файл (на всякий случай)
                            if old_file != file_path:
                                old_file.unlink(missing_ok=True)
                                deleted_count += 1
                                self.logger.debug(f"Удален старый файл: {old_file.name}")
                        except Exception as e:
                            self.logger.warning(f"Не удалось удалить файл {old_file.name}: {e}")

                    if deleted_count > 0:
                        self.logger.info(
                            f"Удалено {deleted_count} старых файлов. "
                            f"Всего файлов: {len(all_files) - deleted_count} (лимит: {max_files})",
                        )
                    else:
                        self.logger.warning(f"Достигнут лимит файлов ({max_files}), но не удалось удалить старые")
                else:
                    self.logger.debug(f"Всего файлов в папке: {len(all_files)} (лимит: {max_files})")

            except Exception as e:
                self.logger.error(f"Ошибка при ограничении количества файлов в {path}: {e}")
                # Продолжаем работу, даже если не удалось очистить старые файлы

            return str(file_path)
        except PermissionError as e:
            self.logger.error(f"Ошибка доступа при сохранении изображения в {folder}: {e}")
            return ""
        except OSError as e:
            self.logger.error(
                f"Ошибка файловой системы при сохранении изображения в {folder}: {e}. "
                f"Возможно, недостаточно места на диске или проблема с файловой системой"
            )
            return ""
        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при сохранении изображения в директорию {folder}: {e}",
                exc_info=True,
            )
            return ""

    async def _get_random_saved_image_async(
        self,
        folder: Path | str = FROGS_DIR,
    ) -> tuple[bytes, str] | None:
        """Асинхронная обёртка над get_random_saved_image для использования в async‑коде.

        Читает файл из файловой системы в отдельном потоке через run_in_executor,
        чтобы избежать блокировки event loop при доступе к диску.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.get_random_saved_image(folder=folder))

    def get_random_saved_image(self, folder: Path | str = FROGS_DIR) -> tuple[bytes, str] | None:
        """Получает случайное изображение из сохраненных файлов.

        Выбирает случайный PNG файл из указанной папки и возвращает его содержимое
        вместе со случайной подписью.

        Args:
            folder: Папка с сохраненными изображениями (по умолчанию FROGS_DIR).

        Returns:
            Кортеж (изображение в байтах, случайная подпись) или None если:
            - папка не существует.
            - в папке нет PNG файлов.
            - произошла ошибка при чтении файла.

        Raises:
            Exception: При ошибке чтения файла или доступа к файловой системе.
        """
        try:
            path = FROGS_DIR if folder == FROGS_DIR else Path(folder)
            if not path.exists():
                self.logger.warning(f"Папка с сохранёнными изображениями не существует: {path}")
                return None

            # Получаем все PNG файлы
            image_files = list(path.glob("*.png"))
            if not image_files:
                self.logger.warning(f"Нет сохраненных изображений в папке {path}")
                return None

            # Выбираем случайный файл
            random_file = random.choice(image_files)

            # Читаем файл
            image_data = random_file.read_bytes()

            # Выбираем случайную подпись
            caption = self.get_random_caption()

            self.logger.info(f"Загружено случайное изображение: {random_file}")
            return image_data, caption

        except Exception as e:
            self.logger.error(f"Ошибка при получении случайного изображения из {folder}: {e}")
            return None
