"""
Celery задачи для Wednesday Frog Bot.

Использует lazy инициализацию сервисов через CeleryServices для fork safety.
Все async ресурсы создаются ПОСЛЕ fork, внутри задач.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import aiohttp
from celery import Task
from celery.signals import worker_shutdown

from bot.wednesday_bot import WednesdayBot
from services.celery_app import celery_app
from services.image_generator import ImageGenerator
from utils.config import config
from utils.logger import get_logger, log_event
from utils.postgres_client import close_postgres_pool, init_postgres_pool
from utils.postgres_schema import ensure_schema
from utils.prometheus_metrics import (
    CELERY_TASK_DURATION_SECONDS,
    CELERY_TASK_FAILURES_TOTAL,
    CELERY_TASK_RETRIES_TOTAL,
    CELERY_TASKS_TOTAL,
)
from utils.redis_client import close_redis, init_redis_pool

P = ParamSpec("P")
R = TypeVar("R")

logger = get_logger(__name__)


def is_retryable_error(error: Exception) -> bool:
    """
    Определяет, является ли ошибка retryable (сетевые ошибки).

    Args:
        error: Исключение для проверки

    Returns:
        True если ошибка retryable, False иначе
    """
    retryable_types = (
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
        OSError,  # Сетевые ошибки на уровне ОС
    )

    # Проверяем тип исключения
    if isinstance(error, retryable_types):
        return True

    # Проверяем строковое представление для дополнительных случаев
    error_str = str(error).lower()
    retryable_keywords = (
        "connection",
        "timeout",
        "network",
        "temporary",
        "retry",
        "503",  # Service Unavailable
        "502",  # Bad Gateway
        "504",  # Gateway Timeout
    )

    return any(keyword in error_str for keyword in retryable_keywords)


# Lazy factories для безопасной инициализации
class CeleryServices:
    """Lazy factory для сервисов Celery.

    Класс обеспечивает безопасную инициализацию сервисов в Celery worker процессах.
    Инициализация происходит внутри задач, после fork worker процесса, что гарантирует:
    - Fork safety (соединения создаются после fork).
    - Отсутствие race conditions.
    - Корректную работу с async клиентами.

    Attributes:
        _bot: Экземпляр WednesdayBot (инициализируется лениво).
        _generator: Экземпляр ImageGenerator (инициализируется лениво).
        _initialized: Флаг инициализации сервисов.
        _init_lock: Блокировка для thread-safe инициализации.
    """

    _bot: WednesdayBot | None = None
    _generator: ImageGenerator | None = None
    _initialized: bool = False
    _init_lock = asyncio.Lock()

    @classmethod
    async def _ensure_initialized(cls) -> None:
        """Инициализирует сервисы один раз (thread-safe).

        Инициализирует Redis и Postgres пулы подключений, создаёт экземпляры
        WednesdayBot и ImageGenerator. Гарантирует, что инициализация выполняется
        только один раз даже при конкурентных вызовах.

        Raises:
            RuntimeError: Если не удалось инициализировать пулы подключений.
        """
        if cls._initialized:
            return

        async with cls._init_lock:
            if cls._initialized:
                return

            # Инициализируем Redis и Postgres (async)
            # ВАЖНО: это происходит ПОСЛЕ fork, в worker процессе
            if config.redis_url:
                await init_redis_pool(url=config.redis_url)
            else:
                await init_redis_pool(
                    host=config.redis_host,
                    port=config.redis_port,
                    db=config.redis_db,
                    password=config.redis_password,
                )
            await init_postgres_pool(min_size=1, max_size=10)
            await ensure_schema()

            # Создаём экземпляры сервисов
            cls._bot = WednesdayBot()
            cls._generator = cls._bot.image_generator

            cls._initialized = True
            logger.info("Celery services initialized in worker process")

    @classmethod
    async def shutdown(cls) -> None:
        """
        Graceful shutdown для async ресурсов.

        Закрывает все соединения при остановке worker:
        - aiohttp sessions
        - redis pool
        - postgres pool

        ⚠️ ВАЖНО: Вызывается автоматически через сигнал worker_shutdown
        """
        if not cls._initialized:
            return

        logger.info("Shutting down Celery services...")

        try:
            if cls._bot:
                # Если у WednesdayBot есть метод aclose()
                if hasattr(cls._bot, "aclose"):
                    await cls._bot.aclose()

            if cls._generator:
                # Если у ImageGenerator есть метод aclose()
                if hasattr(cls._generator, "aclose"):
                    await cls._generator.aclose()

            # Закрываем пулы подключений
            await close_postgres_pool()
            await close_redis()
        except Exception as e:
            logger.error(f"Error during Celery services shutdown: {e}")
        finally:
            cls._bot = None
            cls._generator = None
            cls._initialized = False
            logger.info("Celery services shutdown complete")

    @classmethod
    async def get_bot(cls) -> WednesdayBot:
        """Получает экземпляр WednesdayBot (lazy init).

        Инициализирует сервисы при первом вызове, затем возвращает кэшированный
        экземпляр.

        Returns:
            Экземпляр WednesdayBot.

        Raises:
            RuntimeError: Если не удалось инициализировать WednesdayBot.
        """
        await cls._ensure_initialized()
        if cls._bot is None:
            raise RuntimeError("Failed to initialize WednesdayBot")
        return cls._bot

    @classmethod
    async def get_generator(cls) -> ImageGenerator:
        """Получает экземпляр ImageGenerator (lazy init).

        Инициализирует сервисы при первом вызове, затем возвращает кэшированный
        экземпляр.

        Returns:
            Экземпляр ImageGenerator.

        Raises:
            RuntimeError: Если не удалось инициализировать ImageGenerator.
        """
        await cls._ensure_initialized()
        if cls._generator is None:
            raise RuntimeError("Failed to initialize ImageGenerator")
        return cls._generator


# Регистрируем shutdown handler
@worker_shutdown.connect
def _on_worker_shutdown(sender: object | None = None, **kwargs: object) -> None:
    """Обработчик сигнала остановки worker для graceful shutdown.

    Вызывается автоматически при остановке Celery worker. Выполняет graceful
    shutdown всех async ресурсов (aiohttp sessions, Redis и Postgres пулы).

    Args:
        sender: Отправитель сигнала (обычно Celery app).
        **kwargs: Дополнительные аргументы сигнала.

    Note:
        Для celery[asyncio] worker_shutdown может быть вызван в контексте async,
        но сигнал сам по себе синхронный. Используем безопасный подход с проверкой
        наличия event loop.
    """
    try:
        # Пытаемся получить текущий event loop
        try:
            loop = asyncio.get_running_loop()
            # Если loop запущен, создаём задачу (для celery[asyncio])
            if not loop.is_closed():
                task = asyncio.create_task(CeleryServices.shutdown())
                # Сохраняем ссылку на задачу, чтобы она не была удалена сборщиком мусора
                _ = task
            else:
                # Loop закрыт, создаём новый
                asyncio.run(CeleryServices.shutdown())
        except RuntimeError:
            # Нет запущенного loop, создаём новый
            asyncio.run(CeleryServices.shutdown())
    except Exception as e:
        logger.error(f"Ошибка при вызове shutdown в worker_shutdown handler: {e}")


# Декоратор для логирования Celery задач
def log_celery_task(task_name: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Декоратор для автоматического логирования Celery задач.

    Декоратор добавляет автоматическое логирование начала, завершения и ошибок
    выполнения Celery задач, а также обновляет метрики Prometheus.

    Args:
        task_name: Имя задачи для логирования и метрик.

    Returns:
        Декоратор, который оборачивает асинхронную функцию задачи.

    Example:
        @log_celery_task("my_task")
        async def my_task(self: Task) -> dict[str, Any]:
            ...
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def wrapper(self: Task, *args: object, **kwargs: object) -> Any:  # noqa: ANN401
            start_time = time.time()
            # Получаем request из self (Task)
            request = getattr(self, "request", None)
            task_id = request.id if request else "unknown"

            try:
                # Обновляем метрики Prometheus
                CELERY_TASKS_TOTAL.labels(task_name=task_name, status="started").inc()

                log_event(
                    event="celery_task_started",
                    status="in_progress",
                    extra={
                        "task_name": task_name,
                        "task_id": task_id,
                    },
                    level="info",
                    message=f"Celery задача {task_name} запущена (task_id={task_id})",
                )

                result = await func(self, *args, **kwargs)

                elapsed = time.time() - start_time

                # Обновляем метрики Prometheus
                CELERY_TASKS_TOTAL.labels(task_name=task_name, status="success").inc()
                CELERY_TASK_DURATION_SECONDS.labels(task_name=task_name).observe(elapsed)

                log_event(
                    event="celery_task_success",
                    status="ok",
                    latency_ms=round(elapsed * 1000),
                    extra={
                        "task_name": task_name,
                        "task_id": task_id,
                    },
                    level="info",
                    message=f"Celery задача {task_name} завершена успешно за {elapsed:.2f}с",
                )

                return result

            except Exception as e:
                elapsed = time.time() - start_time

                # Обновляем метрики Prometheus
                error_type = type(e).__name__
                CELERY_TASKS_TOTAL.labels(task_name=task_name, status="failed").inc()
                CELERY_TASK_FAILURES_TOTAL.labels(task_name=task_name, error_type=error_type).inc()

                log_event(
                    event="celery_task_failed",
                    status="error",
                    latency_ms=round(elapsed * 1000),
                    extra={
                        "task_name": task_name,
                        "task_id": task_id,
                        "error": str(e),
                    },
                    level="error",
                    message=f"Celery задача {task_name} завершилась с ошибкой: {e}",
                )
                raise

        return wrapper

    return decorator


@celery_app.task(
    bind=True,
    name="wednesday.send_frog",
    # ⚠️ УЛУЧШЕНО: retry только для сетевых ошибок, не для всех Exception
    autoretry_for=(
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
    ),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут (hard limit)
    options={"queue": "wednesday"},  # Явно указываем очередь
)
@log_celery_task("send_wednesday_frog")
async def send_wednesday_frog_task(self: Task, slot_time: str | None = None) -> dict[str, Any]:
    """Celery задача для отправки изображения жабы.

    Выполняет отправку изображения жабы всем подписанным пользователям в указанное
    время слота. Использует lazy инициализацию сервисов через CeleryServices.

    Args:
        self: Экземпляр Celery Task.
        slot_time: Время слота в формате "HH:MM" или None для текущего времени.

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("success" или "error").
        - slot_time: Время слота, в которое была выполнена отправка.

    Raises:
        Exception: При ошибке отправки или инициализации сервисов.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    try:
        # Lazy инициализация внутри задачи (после fork, безопасно)
        bot = await CeleryServices.get_bot()
        await bot.send_wednesday_frog(slot_time=slot_time)

        return {"status": "success", "slot_time": slot_time}
    except Exception as e:
        # ⚠️ ВАЖНО: Кастомная фильтрация retryable ошибок
        if is_retryable_error(e):
            # Обновляем метрики retry
            CELERY_TASK_RETRIES_TOTAL.labels(task_name="send_wednesday_frog").inc()
            # Retry только для сетевых ошибок
            raise self.retry(exc=e) from e
        else:
            # Бизнес-логические ошибки не retry, сразу падаем
            # После max_retries задача уйдёт в DLQ
            raise


@celery_app.task(
    bind=True,
    name="wednesday.generate_image",
    # ⚠️ УЛУЧШЕНО: retry только для сетевых ошибок через кастомную логику
    autoretry_for=(Exception,),  # Принимаем все, но фильтруем через is_retryable_error
    retry_kwargs={"max_retries": 2, "countdown": 30},
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=120,  # 2 минуты
    time_limit=150,  # 2.5 минуты (hard limit)
    options={"queue": "images"},  # Явно указываем очередь
    # ⚠️ ВАЖНО: Dead Letter Queue для задач, которые упали 2 раза
    reject_on_worker_lost=True,
    acks_late=True,
)
@log_celery_task("generate_frog_image")
async def generate_frog_image_task(self: Task, user_id: int | None = None) -> dict[str, Any]:
    """Celery задача для генерации изображения жабы.

    Выполняет генерацию изображения жабы через ImageGenerator. Использует lazy
    инициализацию сервисов через CeleryServices.

    Args:
        self: Экземпляр Celery Task.
        user_id: ID пользователя, для которого выполняется генерация (опционально).

    Returns:
        Словарь с результатом генерации, содержащий:
        - status: Статус выполнения ("success" или "failed").
        - image_size: Размер сгенерированного изображения в байтах (при успехе).

    Raises:
        Exception: При ошибке генерации или инициализации сервисов.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    try:
        # Lazy инициализация внутри задачи (после fork, безопасно)
        generator = await CeleryServices.get_generator()
        result = await generator.generate_frog_image(user_id=user_id)

        if result:
            image_data, _caption = result
            return {
                "status": "success",
                "image_size": len(image_data),
            }
        else:
            return {"status": "failed", "error": "Генерация вернула None"}
    except Exception as e:
        # ⚠️ ВАЖНО: Кастомная фильтрация retryable ошибок
        if is_retryable_error(e):
            # Обновляем метрики retry
            CELERY_TASK_RETRIES_TOTAL.labels(task_name="generate_frog_image").inc()
            # Retry только для сетевых ошибок
            raise self.retry(exc=e) from e
        else:
            # Бизнес-логические ошибки не retry, сразу падаем
            # После max_retries задача уйдёт в DLQ
            raise


@celery_app.task(
    bind=True,
    name="wednesday.send_frog_manual",
    autoretry_for=(
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
    ),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут (hard limit)
    options={"queue": "wednesday"},
)
@log_celery_task("send_frog_manual")
async def send_frog_manual(
    self: Task,
    chat_id: int,
    user_id: int,
    status_message_id: int | None = None,
) -> dict[str, Any]:
    """Celery задача для отправки изображения жабы по ручной команде /frog.

    Выполняет генерацию и отправку изображения жабы конкретному пользователю.
    Использует lazy инициализацию сервисов через CeleryServices.

    Args:
        self: Экземпляр Celery Task.
        chat_id: ID чата для отправки изображения.
        user_id: ID пользователя (для генерации и логирования).
        status_message_id: ID статусного сообщения для удаления (опционально).

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("success" или "failed").

    Raises:
        Exception: При ошибке генерации, отправки или инициализации сервисов.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    # Константы для сообщений
    MAX_TRACE_LENGTH = 1500
    MAX_MESSAGE_LENGTH = 4000
    MAX_ERROR_DETAILS_LENGTH = 500

    try:
        # Lazy инициализация внутри задачи (после fork, безопасно)
        bot_instance = await CeleryServices.get_bot()
        generator = bot_instance.image_generator

        # Генерируем изображение
        result = await generator.generate_frog_image(user_id=user_id)

        if result:
            image_data, caption = result

            # Отправляем изображение
            await bot_instance.application.bot.send_photo(
                chat_id=chat_id,
                photo=image_data,
                caption=caption,
            )

            # Сохраняем локально
            try:
                saved_path = generator.save_image_locally(image_data, prefix="frog")
                if saved_path:
                    logger.info(f"Изображение сохранено локально: {saved_path}")
            except Exception:
                # Ошибка локального сохранения не критична
                pass

            # Инкрементируем usage
            if bot_instance.usage:
                await bot_instance.usage.increment(1)

            # Удаляем статусное сообщение
            if status_message_id:
                try:
                    await bot_instance.application.bot.delete_message(
                        chat_id=chat_id,
                        message_id=status_message_id,
                    )
                except Exception:
                    # Игнорируем ошибки удаления статуса
                    pass

            logger.info(f"Изображение жабы успешно отправлено пользователю {user_id} в чат {chat_id}")
            return {"status": "success"}

        else:
            # Генерация не удалась - fallback логика
            error_details = f"Не удалось сгенерировать изображение для пользователя {user_id}"
            logger.error(error_details)

            # Удаляем статусное сообщение
            if status_message_id:
                try:
                    await bot_instance.application.bot.delete_message(
                        chat_id=chat_id,
                        message_id=status_message_id,
                    )
                except Exception:
                    pass

            # Отправляем дружелюбное сообщение пользователю
            friendly_message = (
                "🐸 К сожалению, не удалось сгенерировать новую картинку.\n"
                "Но не расстраивайтесь! Вот случайная картинка из архива! 🎲"
            )
            try:
                await bot_instance.application.bot.send_message(
                    chat_id=chat_id,
                    text=friendly_message,
                )
            except Exception as e:
                logger.error(f"Не удалось отправить дружелюбное сообщение: {e}")

            # Отправляем случайное изображение из сохраненных
            fallback_image = generator.get_random_saved_image()
            if fallback_image:
                fallback_image_data, fallback_caption = fallback_image
                try:
                    await bot_instance.application.bot.send_photo(
                        chat_id=chat_id,
                        photo=fallback_image_data,
                        caption=fallback_caption,
                    )
                    logger.info(f"Случайное изображение отправлено пользователю {user_id} как fallback")
                except Exception as e:
                    logger.error(f"Не удалось отправить fallback изображение: {e}")
            else:
                logger.warning("Нет сохраненных изображений для отправки как fallback")

            # Уведомляем администраторов
            from utils.admins_store import AdminsStore

            admins_store = AdminsStore()
            all_admins = await admins_store.list_all_admins()
            if all_admins:
                admin_message = (
                    "🔴 Ошибка генерации изображения по команде /frog\n\n"
                    f"Пользователь: {user_id}\n"
                    f"Детали: {error_details}\n"
                    "Возможные причины: достигнут лимит API, circuit breaker активен, ошибка генерации\n\n"
                    "Пользователю отправлено дружелюбное сообщение и случайное изображение из архива."
                )
                for admin_id in all_admins:
                    try:
                        await bot_instance.application.bot.send_message(
                            chat_id=admin_id,
                            text=admin_message,
                        )
                    except Exception as admin_error:
                        logger.error(
                            f"Не удалось отправить сообщение об ошибке админу {admin_id}: {admin_error}",
                        )

            return {"status": "failed", "error": "Генерация вернула None"}

    except Exception as e:
        error_type = type(e).__name__
        error_str = str(e)

        # Определяем тип ошибки для более информативного сообщения
        if "ConnectError" in error_type or "ConnectionError" in error_type or "Connection" in error_str:
            error_details = (
                f"Ошибка подключения к API при обработке команды /frog для пользователя {user_id}.\n"
                f"Тип: {error_type}\n"
                f"Детали: {error_str[:200]}\n\n"
                "Возможные причины:\n"
                "- Проблемы с интернет-соединением\n"
                "- Kandinsky API временно недоступен\n"
                "- Проблемы с прокси (если используется)\n"
                "- Блокировка доступа на стороне провайдера"
            )
        else:
            error_details = (
                f"Произошла ошибка при обработке команды /frog для пользователя {user_id}.\n"
                f"Тип: {error_type}\nДетали: {error_str[:200]}"
            )

        logger.error(f"Ошибка при обработке /frog: {error_type} - {error_str}", exc_info=True)

        # Удаляем статусное сообщение
        if status_message_id:
            try:
                bot_instance = await CeleryServices.get_bot()
                await bot_instance.application.bot.delete_message(
                    chat_id=chat_id,
                    message_id=status_message_id,
                )
            except Exception:
                pass

        # Отправляем дружелюбное сообщение пользователю
        try:
            bot_instance = await CeleryServices.get_bot()
            friendly_message = (
                "🐸 К сожалению, произошла ошибка при генерации.\n"
                "Но не расстраивайтесь! Вот случайная картинка из архива! 🎲"
            )
            await bot_instance.application.bot.send_message(
                chat_id=chat_id,
                text=friendly_message,
            )

            # Отправляем случайное изображение из сохраненных
            generator = bot_instance.image_generator
            fallback_image = generator.get_random_saved_image()
            if fallback_image:
                fallback_image_data, fallback_caption = fallback_image
                await bot_instance.application.bot.send_photo(
                    chat_id=chat_id,
                    photo=fallback_image_data,
                    caption=fallback_caption,
                )
                logger.info(f"Случайное изображение отправлено пользователю {user_id} как fallback")
        except Exception as send_error:
            logger.error(f"Не удалось отправить fallback сообщение/изображение: {send_error}")

        # Сохраняем оригинальную ошибку перед обработкой уведомлений админам
        original_error = e

        # Уведомляем администраторов
        try:
            bot_instance = await CeleryServices.get_bot()
            import traceback

            from utils.admins_store import AdminsStore

            admins_store = AdminsStore()
            all_admins = await admins_store.list_all_admins()
            if all_admins:
                full_error = traceback.format_exc()
                # Обрезаем трейс до последних MAX_TRACE_LENGTH символов
                if len(full_error) > MAX_TRACE_LENGTH:
                    full_error = "..." + full_error[-MAX_TRACE_LENGTH:]

                admin_message = (
                    "🔴 Ошибка при обработке команды /frog\n\n"
                    f"Пользователь: {user_id}\n"
                    f"Детали: {error_details}\n\n"
                    f"Трейс (последние {MAX_TRACE_LENGTH} символов):\n{full_error}\n\n"
                    "Пользователю отправлено дружелюбное сообщение и случайное изображение из архива."
                )

                # Разбиваем длинные сообщения на части
                for admin_id in all_admins:
                    try:
                        if len(admin_message) > MAX_MESSAGE_LENGTH:
                            # Отправляем короткую версию без полного трейса
                            short_message = (
                                "🔴 Ошибка при обработке команды /frog\n\n"
                                f"Пользователь: {user_id}\n"
                                f"Детали: {error_details[:MAX_ERROR_DETAILS_LENGTH]}\n\n"
                                "⚠️ Полный трейс слишком длинный, смотрите логи.\n\n"
                                "Пользователю отправлено дружелюбное сообщение и случайное изображение из архива."
                            )
                            await bot_instance.application.bot.send_message(
                                chat_id=admin_id,
                                text=short_message,
                            )
                        else:
                            await bot_instance.application.bot.send_message(
                                chat_id=admin_id,
                                text=admin_message,
                            )
                    except Exception as admin_error:
                        error_str = str(admin_error)
                        # Если ошибка "Message is too long", отправляем сокращенную версию
                        if "too long" in error_str.lower():
                            try:
                                short_message = (
                                    "🔴 Ошибка при обработке команды /frog\n\n"
                                    f"Пользователь: {user_id}\n"
                                    f"Детали: {error_details[:MAX_ERROR_DETAILS_LENGTH]}\n\n"
                                    "⚠️ Полный трейс слишком длинный для отправки, смотрите логи.\n\n"
                                    "Пользователю отправлено дружелюбное сообщение и "
                                    "случайное изображение из архива."
                                )
                                await bot_instance.application.bot.send_message(
                                    chat_id=admin_id,
                                    text=short_message,
                                )
                            except Exception as retry_error:
                                logger.error(
                                    f"Не удалось отправить даже сокращенное сообщение админу {admin_id}: {retry_error}",
                                )
                        else:
                            logger.error(
                                f"Не удалось отправить сообщение об ошибке админу {admin_id}: {admin_error}",
                            )
        except Exception as admin_notification_error:
            logger.error(f"Ошибка при отправке сообщений админам: {admin_notification_error}")

        # ⚠️ ВАЖНО: Кастомная фильтрация retryable ошибок
        if is_retryable_error(original_error):
            # Обновляем метрики retry
            CELERY_TASK_RETRIES_TOTAL.labels(task_name="send_frog_manual").inc()
            # Retry только для сетевых ошибок
            raise self.retry(exc=original_error) from original_error
        else:
            # Бизнес-логические ошибки не retry, сразу падаем
            # После max_retries задача уйдёт в DLQ
            raise


@celery_app.task(
    bind=True,
    name="wednesday.daily_cleanup",
    soft_time_limit=600,  # 10 минут
    time_limit=720,  # 12 минут
)
@log_celery_task("daily_cleanup")
async def daily_cleanup_task(self: Task) -> dict[str, Any]:
    """Ежедневная задача очистки старых данных.

    Выполняет очистку устаревших данных:
    - Очистка старых записей dispatch_registry.
    - Очистка временных файлов.
    - Очистка кэша.

    Args:
        self: Экземпляр Celery Task.

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("success" или "error").

    Raises:
        Exception: При ошибке выполнения очистки.
    """
    try:
        # Lazy инициализация для доступа к сервисам (для инициализации пулов)
        _ = await CeleryServices.get_bot()

        # Очистка старых записей dispatch_registry
        from utils.dispatch_registry import DispatchRegistry

        registry = DispatchRegistry()
        await registry.cleanup_old()

        logger.info("Daily cleanup task completed successfully")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in daily cleanup task: {e}")
        raise


@celery_app.task(
    bind=True,
    name="wednesday.daily_statistics",
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут
)
@log_celery_task("daily_statistics")
async def daily_statistics_task(self: Task) -> dict[str, Any]:
    """Ежедневная задача сбора статистики.

    Выполняет сбор и агрегацию статистики за день:
    - Агрегация метрик из metrics_events.
    - Отправка отчётов (если настроено).
    - Обновление дашбордов (если настроено).

    Args:
        self: Экземпляр Celery Task.

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("success" или "error").

    Raises:
        Exception: При ошибке сбора статистики.
    """
    try:
        # Lazy инициализация для доступа к сервисам (для инициализации пулов)
        _ = await CeleryServices.get_bot()

        # Здесь можно добавить логику сбора статистики
        # Например, агрегация метрик из metrics_events

        logger.info("Daily statistics task completed successfully")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in daily statistics task: {e}")
        raise


@celery_app.task(
    bind=True,
    name="wednesday.beat_heartbeat",
)
def beat_heartbeat(self: Task) -> dict[str, Any]:
    """Задача для heartbeat Beat (touch файл в tmpfs).

    Создаёт или обновляет файл heartbeat для мониторинга работы Celery Beat.
    Используется healthcheck-системами для проверки активности планировщика.

    Args:
        self: Экземпляр Celery Task.

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("ok").

    Note:
        Ошибки при создании файла игнорируются, так как healthcheck сам проверит
        наличие файла.
    """
    import os

    heartbeat_path = "/tmp/beat-hb"
    try:
        # Touch файл (создать или обновить mtime)
        with open(heartbeat_path, "a", encoding="utf-8"):
            os.utime(heartbeat_path, None)
    except Exception:
        # Игнорируем ошибки - healthcheck сам проверит наличие файла
        pass

    return {"status": "ok"}
