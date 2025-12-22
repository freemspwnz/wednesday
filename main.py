"""
Главный файл запуска Wednesday Frog Bot.
Точка входа в приложение с обработкой ошибок и graceful shutdown.
"""

import asyncio
import atexit
import signal
import sys
import types
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from prometheus_client import start_http_server

from bot.support_bot import SupportBot
from infra.container import build_bot
from infra.database.postgres_client import get_postgres_pool, init_postgres_pool
from infra.database.postgres_schema import ensure_schema
from infra.logging.logger import get_logger, log_event
from infra.redis.redis_client import get_redis, init_redis_pool, redis_available
from shared.config_v2 import ConfigV2

# Создаём экземпляр ConfigV2 при импорте модуля
config = ConfigV2()

if TYPE_CHECKING:
    from loguru import Logger as LoggerType

    from bot.wednesday_bot import WednesdayBot

# Константы вместо чисел
SLEEP_BETWEEN_BOTS_SECONDS = 5.0


class BotRunner:
    """
    Класс для управления запуском и остановкой бота.

    Обеспечивает:
    - Graceful shutdown при получении сигналов
    - Обработку ошибок запуска
    - Логирование состояния приложения
    - Гарантированное закрытие ресурсов через context manager
    """

    def __init__(self) -> None:
        """Инициализация runner'а бота."""
        self.logger = get_logger(__name__)
        self.logger.info("Начало инициализации BotRunner")
        self.bot: WednesdayBot | None = None
        self.support_bot: SupportBot | None = None
        self.shutdown_event: asyncio.Event = asyncio.Event()
        self.should_stop: bool = False
        self.request_start_main_event: asyncio.Event = asyncio.Event()
        self.pending_startup_edit: dict[str, Any] | None = None
        self.pending_shutdown_edit: dict[str, Any] | None = None
        # Регистрируем cleanup через atexit для гарантированного вызова при завершении
        atexit.register(self._sync_cleanup)
        self.logger.info("BotRunner успешно инициализирован")

    def _sync_cleanup(self) -> None:
        """
        Синхронная обёртка для cleanup, вызываемая через atexit.

        Пытается вызвать асинхронный cleanup, если event loop доступен.
        """
        try:
            # Пытаемся получить текущий event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если loop работает, создаём задачу для cleanup
                _ = asyncio.create_task(self._cleanup())  # noqa: RUF006 - задача запускается в фоне
            else:
                # Если loop не работает, запускаем cleanup синхронно
                loop.run_until_complete(self._cleanup())
        except RuntimeError:
            # Нет event loop - пытаемся создать новый для cleanup
            try:
                asyncio.run(self._cleanup())
            except Exception as e:
                # Если не удалось, просто логируем
                print(f"Не удалось выполнить cleanup при завершении: {e}")
        except Exception as e:
            # Любая другая ошибка - логируем и продолжаем
            print(f"Ошибка при cleanup через atexit: {e}")

    def setup_signal_handlers(self) -> None:
        """
        Настраивает обработчики сигналов для graceful shutdown.
        """
        self.logger.info("Начало настройки обработчиков сигналов")

        # Обработчики для SIGINT (Ctrl+C) и SIGTERM
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._signal_handler)
                self.logger.info(f"Обработчик сигнала {sig} установлен")
            except Exception as e:
                self.logger.error(f"Ошибка при установке обработчика сигнала {sig}: {e}", exc_info=True)

        self.logger.info("Обработчики сигналов успешно настроены")

    def _signal_handler(self, signum: int | None = None, frame: types.FrameType | None = None) -> None:
        """
        Обработчик сигналов для graceful shutdown.

        Args:
            signum: Номер сигнала
            frame: Текущий стекадрес
        """
        self.logger.info(f"Начало обработки сигнала: signum={signum}")
        try:
            print("\n🛑 Получен сигнал остановки, начинаю graceful shutdown...")

            # Устанавливаем флаг остановки
            self.should_stop = True
            self.logger.info("Флаг should_stop установлен в True")

            # Устанавливаем событие для остановки
            if hasattr(self, "shutdown_event") and self.shutdown_event is not None:
                self.shutdown_event.set()
                self.logger.info("Событие shutdown_event установлено")

            # Попытка логирования (безопасно)
            if hasattr(self, "logger") and self.logger is not None:
                try:
                    self.logger.info("Получен сигнал остановки, начинаю graceful shutdown")
                except Exception:
                    pass  # Игнорируем ошибки логирования

            self.logger.info("Обработка сигнала завершена успешно")

        except Exception as e:
            # В случае любой ошибки в обработчике сигналов, просто выводим в консоль
            print(f"Ошибка в обработчике сигналов: {e}")
            if hasattr(self, "logger") and self.logger is not None:
                try:
                    self.logger.error(f"Ошибка в обработчике сигналов: {e}", exc_info=True)
                except Exception:
                    pass

    async def run(self) -> None:
        """
        Основной метод запуска бота.
        """
        self.logger.info("Начало выполнения метода run()")

        try:
            # Проверяем конфигурацию и инициализируем Redis (если доступен)
            self.logger.info("Проверка требований перед запуском")
            self._check_requirements()
            self.logger.info("Проверка требований завершена успешно")
            await self._init_redis_if_configured()
            await self._init_postgres_if_configured()
            await ensure_schema()

            # Общий цикл: сначала пробуем запускать основной бот; при остановке — включаем SupportBot
            self.logger.info("Настройка обработчиков сигналов в event loop")
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    # Используем функцию-фабрику для правильного замыкания
                    def create_signal_handler(signal_num: signal.Signals) -> Callable[[], None]:
                        def handler() -> None:
                            self._signal_handler(signal_num, None)

                        return handler

                    loop.add_signal_handler(sig, create_signal_handler(sig))
                    self.logger.info(f"Обработчик сигнала {sig} добавлен в event loop")
                except (ValueError, RuntimeError, AttributeError) as e:
                    self.logger.warning(f"Не удалось установить обработчик сигнала {sig}: {e}", exc_info=True)

            while not self.should_stop and not self.shutdown_event.is_set():
                # Этап 1: всегда запускаем SupportBot первым
                self.logger.info("[Supervisor] Старт SupportBot (режим по умолчанию)")
                self.request_start_main_event.clear()

                async def request_start_main(payload: dict[str, Any]) -> None:
                    self.logger.info(
                        f"[Supervisor] Получен запрос запуска основного бота из SupportBot, payload={payload}",
                    )
                    self.pending_startup_edit = payload or None
                    self.request_start_main_event.set()
                    self.logger.info("[Supervisor] Событие request_start_main_event установлено")
                    await asyncio.sleep(0)

                self.logger.info("Создание экземпляра SupportBot")
                self.support_bot = SupportBot(request_start_main=request_start_main)
                # Если есть отложенное редактирование для статуса остановки основного — передадим SupportBot
                try:
                    if isinstance(self.pending_shutdown_edit, dict):
                        self.logger.info(f"Передача pending_shutdown_edit в SupportBot: {self.pending_shutdown_edit}")
                        self.support_bot.pending_shutdown_edit = self.pending_shutdown_edit
                        self.pending_shutdown_edit = None
                except Exception as e:
                    self.logger.error(f"Ошибка при передаче pending_shutdown_edit: {e}", exc_info=True)
                    self.pending_shutdown_edit = None
                self.logger.info("Запуск SupportBot в фоновой задаче")
                support_task = asyncio.create_task(self.support_bot.start())
                self.logger.info("SupportBot запущен в фоновой задаче")

                # Ждём либо сигнал завершения процесса, либо запрос запуска основного
                while True:
                    if self.should_stop or self.shutdown_event.is_set():
                        self.logger.info("[Supervisor] Сигнал завершения в режиме SupportBot — завершаем работу")
                        await self._stop_support_bot()
                        if not support_task.done():
                            support_task.cancel()
                        return
                    if self.request_start_main_event.is_set():
                        break
                    await asyncio.sleep(0.1)

                # Переключение: останавливаем SupportBot, запускаем основной бот
                self.logger.info("[Supervisor] Переключение: SupportBot -> основной бот")
                self.logger.info("[Supervisor] Остановка SupportBot перед запуском основного бота")
                await self._stop_support_bot()
                if not support_task.done():
                    self.logger.info("[Supervisor] Отмена задачи SupportBot")
                    support_task.cancel()
                # Дадим немного времени освободить getUpdates
                self.logger.info(
                    f"[Supervisor] Ожидание {SLEEP_BETWEEN_BOTS_SECONDS} секунд перед запуском основного бота",
                )
                await asyncio.sleep(SLEEP_BETWEEN_BOTS_SECONDS)
                self.logger.info("[Supervisor] Ожидание завершено, запускаю основной бот")

                # Этап 2: запускаем основной бот
                self.logger.info("[Supervisor] Создание экземпляра WednesdayBot")
                postgres_pool = get_postgres_pool()
                self.bot = build_bot(config, db_pool=postgres_pool)
                try:
                    if self.pending_startup_edit:
                        self.logger.info(
                            f"[Supervisor] Передача pending_startup_edit в основной бот: {self.pending_startup_edit}",
                        )
                    self.bot.pending_startup_edit = self.pending_startup_edit
                except Exception as e:
                    self.logger.error(f"[Supervisor] Ошибка при передаче pending_startup_edit: {e}", exc_info=True)
                try:
                    self.logger.info("[Supervisor] Получение информации о боте перед запуском")
                    bot_info = await self.bot.get_bot_info()
                    self.logger.info(f"[Supervisor] Информация о боте получена: {bot_info}")
                except Exception as e:
                    self.logger.warning(f"[Supervisor] Не удалось получить информацию о боте: {e}", exc_info=True)
                self.logger.info("[Supervisor] Запуск основного бота в фоновой задаче")
                bot_task = asyncio.create_task(self.bot.start())
                self.logger.info("[Supervisor] Запуск задачи ожидания shutdown")
                shutdown_task = asyncio.create_task(self._wait_for_shutdown())

                self.logger.info("[Supervisor] Ожидание завершения bot_task или shutdown_task")
                done, pending = await asyncio.wait(
                    [bot_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                self.logger.info(f"[Supervisor] Одна из задач завершена: done={len(done)}, pending={len(pending)}")

                # Если пришёл сигнал — останавливаем основной и снова уходим в SupportBot
                if self.should_stop or self.shutdown_event.is_set():
                    self.logger.info(
                        "[Supervisor] Сигнал завершения при активном основном — "
                        "останавливаю основной и возвращаюсь к SupportBot",
                    )
                    # Сохраним отложенное редактирование статуса остановки
                    try:
                        if hasattr(self.bot, "pending_shutdown_edit") and isinstance(
                            self.bot.pending_shutdown_edit,
                            dict,
                        ):
                            self.logger.info(
                                f"[Supervisor] Сохранение pending_shutdown_edit: {self.bot.pending_shutdown_edit}",
                            )
                            self.pending_shutdown_edit = self.bot.pending_shutdown_edit
                    except Exception as e:
                        self.logger.error(
                            f"[Supervisor] Ошибка при сохранении pending_shutdown_edit: {e}",
                            exc_info=True,
                        )
                    self.logger.info("[Supervisor] Остановка основного бота")
                    await self._stop_bot()
                    self.bot = None
                    if not bot_task.done():
                        self.logger.info("[Supervisor] Отмена задачи основного бота")
                        bot_task.cancel()
                    # Сбрасываем флаги остановки, чтобы НЕ завершать приложение и вернуться к SupportBot
                    self.logger.info("[Supervisor] Сброс флагов остановки для возврата к SupportBot")
                    self.should_stop = False
                    self.shutdown_event = asyncio.Event()
                    # Небольшая пауза, чтобы освободить getUpdates/соединения
                    self.logger.info(
                        f"[Supervisor] Ожидание {SLEEP_BETWEEN_BOTS_SECONDS} секунд перед возвратом к SupportBot",
                    )
                    await asyncio.sleep(SLEEP_BETWEEN_BOTS_SECONDS)
                    self.logger.info("[Supervisor] Возврат к началу цикла для запуска SupportBot")
                    # Переходим к началу while, где снова запустится SupportBot
                    continue
                else:
                    # Основной завершился сам (ошибка или /stop) — возвращаемся к SupportBot
                    self.logger.warning("[Supervisor] Основной бот остановлен. Запуск SupportBot")
                    # Сохраним отложенное редактирование статуса остановки
                    try:
                        if hasattr(self.bot, "pending_shutdown_edit") and isinstance(
                            self.bot.pending_shutdown_edit,
                            dict,
                        ):
                            self.logger.info(
                                f"[Supervisor] Сохранение pending_shutdown_edit: {self.bot.pending_shutdown_edit}",
                            )
                            self.pending_shutdown_edit = self.bot.pending_shutdown_edit
                    except Exception as e:
                        self.logger.error(
                            f"[Supervisor] Ошибка при сохранении pending_shutdown_edit: {e}",
                            exc_info=True,
                        )
                    self.logger.info("[Supervisor] Остановка основного бота после его завершения")
                    await self._stop_bot()
                    self.bot = None
                    try:
                        if not bot_task.done():
                            self.logger.info("[Supervisor] Отмена и ожидание завершения задачи основного бота")
                            bot_task.cancel()
                            await bot_task
                    except Exception as e:
                        self.logger.error(f"[Supervisor] Ошибка при отмене задачи основного бота: {e}", exc_info=True)
                    self.logger.info(
                        f"[Supervisor] Ожидание {SLEEP_BETWEEN_BOTS_SECONDS} секунд "
                        "перед повторным запуском SupportBot",
                    )
                    await asyncio.sleep(SLEEP_BETWEEN_BOTS_SECONDS)
                    # Сбросим сигналы перед повторным запуском SupportBot
                    self.logger.info("[Supervisor] Сброс флагов остановки перед повторным запуском SupportBot")
                    self.should_stop = False
                    self.shutdown_event = asyncio.Event()

            self.logger.info("Wednesday Frog Bot (supervisor) успешно завершил работу")

        except Exception as e:
            # Более подробное логирование ошибки
            import traceback

            error_details = traceback.format_exc()
            self.logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
            self.logger.error(f"Подробности ошибки:\n{error_details}")
            self.logger.info("Выполнение очистки ресурсов после ошибки")
            await self._cleanup()
            raise

    def _check_requirements(self) -> None:
        """
        Проверяет наличие необходимых файлов и настроек.
        """
        self.logger.info("Начало проверки требований для запуска")

        # На этом этапе переменные окружения уже загружены через ConfigV2:
        # сначала из окружения контейнера, затем при необходимости fallback из .env.
        # Здесь мы только логируем наличие ключевых обязательных переменных.
        self.logger.info("Проверка конфигурации: логирование обязательных переменных окружения")
        try:
            # Проверяем, что все обязательные переменные загружены
            telegram_token = config.telegram.bot_token
            kandinsky_api_key = config.kandinsky.api_key
            kandinsky_secret_key = config.kandinsky.secret_key
            chat_id = config.telegram.chat_id
            admin_chat_id = config.telegram.admin_chat_id
            self.logger.info("Все обязательные переменные конфигурации загружены успешно")
            self.logger.info(f"TELEGRAM_BOT_TOKEN: {'установлен' if telegram_token else 'не установлен'}")
            self.logger.info(f"KANDINSKY_API_KEY: {'установлен' if kandinsky_api_key else 'не установлен'}")
            self.logger.info(f"KANDINSKY_SECRET_KEY: {'установлен' if kandinsky_secret_key else 'не установлен'}")
            self.logger.info(f"CHAT_ID: {'установлен' if chat_id else 'не установлен'}")
            self.logger.info(f"ADMIN_CHAT_ID: {'установлен' if admin_chat_id else 'не установлен'}")
        except Exception as e:
            self.logger.error(f"Ошибка в конфигурации: {e}", exc_info=True)
            sys.exit(1)
        self.logger.info("Проверка требований завершена успешно")

    async def _init_redis_if_configured(self) -> None:
        """
        Пытается инициализировать глобальный Redis‑клиент.

        Важно:
        - Redis не является жёсткой зависимостью — при ошибке инициализации
          приложение продолжает работу в деградированном режиме с in‑memory
          fallback'ами, а все Redis‑зависимые сервисы логируют режим работы.
        """
        self.logger.info("Пробую инициализировать Redis‑клиент (если задан конфиг)")
        url = config.redis.url
        try:
            if url:
                await init_redis_pool(url=url)
            else:
                await init_redis_pool(
                    host=config.redis.host,
                    port=config.redis.port,
                    db=config.redis.db,
                    password=config.redis.password,
                )
            self.logger.info(
                f"Redis успешно инициализирован, режим работы: redis_available={redis_available()}",
            )
        except Exception as exc:
            # Явно фиксируем, что работаем без Redis, но не прерываем запуск.
            self.logger.warning(f"Redis недоступен при старте ({exc!s}). Продолжаем в режиме fallback (in‑memory).")

    async def _init_postgres_if_configured(self) -> None:
        """
        Инициализирует пул подключений к Postgres.

        Важно:
        - Postgres используется для постоянного хранения данных (чаты, админы, лимиты и т.п.).
        - При ошибке инициализации запуск приложения прерывается, чтобы избежать работы
          в полудеградированном состоянии без персистентности.
        """
        self.logger.info("Пробую инициализировать пул Postgres")
        try:
            # Бот в основном IO‑bound, поэтому достаточно небольшого пула.
            await init_postgres_pool(min_size=1, max_size=10, config=config)
            self.logger.info("Postgres успешно инициализирован")
        except Exception as exc:
            self.logger.error(
                "Не удалось инициализировать Postgres: "
                f"{exc}. Проверьте доступность БД и переменные окружения POSTGRES_*. ",
            )
            raise

    async def _cleanup(self) -> None:
        """
        Выполняет очистку ресурсов при завершении работы.
        """
        self.logger.info("Начало очистки ресурсов")

        if self.bot and getattr(self.bot, "is_running", False):
            self.logger.info("Остановка основного бота при очистке")
            try:
                await self.bot.stop()
                self.logger.info("Основной бот успешно остановлен")
            except Exception as e:
                self.logger.error(f"Ошибка при остановке бота: {e}", exc_info=True)
        elif self.bot and hasattr(self.bot, "services"):
            # Если бот не был остановлен через stop(), но services доступны, вызываем cleanup напрямую
            try:
                await self.bot.services.cleanup()
                self.logger.info("Ресурсы BotServices закрыты через _cleanup()")
            except Exception as e:
                self.logger.warning(f"Ошибка при cleanup ресурсов BotServices: {e}")
        self.bot = None
        self.logger.info("Ссылка на основной бот очищена")

        if self.support_bot and getattr(self.support_bot, "is_running", False):
            self.logger.info("Остановка SupportBot при очистке")
            try:
                await self.support_bot.stop()
                self.logger.info("SupportBot успешно остановлен")
            except Exception as e:
                self.logger.error(f"Ошибка при остановке SupportBot: {e}", exc_info=True)
        self.support_bot = None
        self.logger.info("Ссылка на SupportBot очищена")
        self.logger.info("Очистка ресурсов завершена успешно")

    async def _wait_for_shutdown(self) -> None:
        """
        Ожидает сигнал остановки.
        """
        self.logger.info("Начало ожидания сигнала остановки")
        while not self.should_stop and not self.shutdown_event.is_set():
            await asyncio.sleep(0.1)
        self.logger.info("Получен сигнал остановки, завершение ожидания")

    async def _stop_bot(self) -> None:
        """
        Асинхронно останавливает бота.
        """
        self.logger.info("Начало остановки основного бота")
        if self.bot is None:
            self.logger.info("Основной бот не инициализирован, пропускаю остановку")
            return
        try:
            self.logger.info("Вызов метода stop() основного бота")
            await self.bot.stop()
            self.logger.info("Основной бот успешно остановлен")
        except Exception as e:
            self.logger.error(f"Ошибка при остановке бота: {e}", exc_info=True)

    async def _stop_support_bot(self) -> None:
        self.logger.info("Начало остановки SupportBot")
        try:
            if self.support_bot:
                self.logger.info("Вызов метода stop() SupportBot")
                await self.support_bot.stop()
                self.logger.info("SupportBot успешно остановлен")
            else:
                self.logger.info("SupportBot не инициализирован, пропускаю остановку")
        except Exception as e:
            self.logger.error(f"Ошибка при остановке SupportBot: {e}", exc_info=True)


def _start_prometheus_exporter(logger: "LoggerType") -> None:
    """
    Запускает HTTP‑экспортёр Prometheus для эндпоинта /metrics в отдельном потоке.

    Порт берётся из конфигурации (PROMETHEUS_EXPORTER_PORT). Если переменная
    не задана или содержит некорректное значение, экспортер не запускается.
    """
    port = config.prometheus_exporter_port
    if port is None or port <= 0:
        logger.info("Prometheus‑экспортёр отключён (PROMETHEUS_EXPORTER_PORT не задан или некорректен)")
        log_event(
            event="prometheus_exporter_disabled",
            status="disabled",
            extra={"raw_port_value": port},
            level="info",
            message="HTTP‑экспортёр Prometheus отключён конфигурацией",
        )
        return
    try:
        start_http_server(port)
        logger.info(f"Prometheus /metrics экспортёр запущен на 0.0.0.0:{port}")
        log_event(
            event="prometheus_exporter_started",
            status="ok",
            extra={"port": port},
            level="info",
            message="HTTP‑экспортёр Prometheus успешно запущен",
        )
    except Exception as exc:  # pragma: no cover - защитное логирование
        logger.warning(f"Не удалось запустить Prometheus‑экспортёр на порту {port}: {exc}")
        log_event(
            event="prometheus_exporter_failed",
            status="error",
            extra={"port": port, "error": str(exc)},
            level="warning",
            message="Ошибка запуска HTTP‑экспортёра Prometheus",
        )


def _init_sentry(logger: "LoggerType") -> None:
    """
    Инициализирует Sentry SDK (если задан SENTRY_DSN).

    Используется интеграция asyncio, чтобы корректно перехватывать
    необработанные исключения в асинхронном коде. Для FastAPI‑эндпоинта
    healthcheck и других потенциальных HTTP‑сервисов также подключается
    FastAPI‑интеграция.
    """
    dsn = config.sentry.dsn
    if not dsn:
        logger.info("Sentry отключён (SENTRY_DSN не задан)")
        log_event(
            event="sentry_disabled",
            status="disabled",
            extra={"reason": "missing_dsn"},
            level="info",
            message="Sentry не инициализирован: отсутствует SENTRY_DSN",
        )
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=config.sentry.environment,
            release=config.sentry.release,
            integrations=[
                AsyncioIntegration(),
                FastApiIntegration(),
            ],
            # Трассировку по умолчанию отключаем, чтобы не собирать лишний объём
            # данных без явной настройки. При необходимости её можно включить
            # через переменные окружения.
            traces_sample_rate=0.0,
        )
        logger.info("Sentry SDK успешно инициализирован")
        log_event(
            event="sentry_initialized",
            status="ok",
            extra={
                "environment": config.sentry.environment,
                "release": config.sentry.release,
            },
            level="info",
            message="Sentry SDK успешно инициализирован",
        )
    except Exception as exc:  # pragma: no cover - защитное логирование
        logger.warning(f"Не удалось инициализировать Sentry SDK: {exc!s}")
        log_event(
            event="sentry_init_failed",
            status="error",
            extra={"error": str(exc)},
            level="warning",
            message="Ошибка инициализации Sentry SDK",
        )


def _start_health_server(logger: "LoggerType") -> None:
    """
    Запускает HTTP‑сервер FastAPI с эндпоинтом /health в том же event loop,
    в котором работает Telegram‑бот.

    ВАЖНО:
    - не создаёт отдельный поток и не вызывает asyncio.run;
    - использует реальные Redis/Postgres‑клиенты, инициализированные при старте
      приложения (через utils.redis_client / utils.postgres_client);
    - перед запуском uvicorn прокидывает эти клиенты в FastAPI‑приложение через app.state.
    """
    port = config.healthcheck_port
    if port is None:
        logger.info("HTTP‑healthcheck отключён (HEALTHCHECK_PORT не задан)")
        log_event(
            event="healthcheck_server_disabled",
            status="disabled",
            extra={"raw_port_value": port},
            level="info",
            message="HTTP‑сервер healthcheck отключён конфигурацией",
        )
        return

    try:
        import uvicorn

        from infra.healthcheck import app as health_app

        # Прокидываем реальные клиенты в FastAPI‑приложение healthcheck.
        # Если инициализация не удалась — оставляем None, а сам healthcheck
        # корректно отразит недоступность зависимостей.
        try:
            health_app.state.redis = get_redis()
        except Exception:
            health_app.state.redis = None

        try:
            health_app.state.postgres_pool = get_postgres_pool()
        except Exception:
            health_app.state.postgres_pool = None

        uvicorn_config = uvicorn.Config(
            app=health_app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=False,  # Отключить access log, логировать через middleware
            loop="asyncio",
        )
        server = uvicorn.Server(config=uvicorn_config)

        # Запускаем uvicorn в том же event loop, что и бот, и навешиваем callback
        # для логирования аварийных завершений.
        task = asyncio.create_task(server.serve(), name="healthcheck_server")

        def _on_done(t: asyncio.Task[object]) -> None:
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            if exc is not None:
                logger.error(f"Healthcheck server crashed: {exc!r}")

        task.add_done_callback(_on_done)

        logger.info(f"HTTP‑сервер healthcheck /health запущен на 0.0.0.0:{port}")
        log_event(
            event="healthcheck_server_started",
            status="ok",
            extra={"port": port},
            level="info",
            message="HTTP‑сервер healthcheck успешно запущен",
        )
    except Exception as exc:  # pragma: no cover - защитное логирование
        logger.warning(f"Не удалось запустить HTTP‑сервер healthcheck на порту {port}: {exc!s}")
        log_event(
            event="healthcheck_server_failed",
            status="error",
            extra={"port": port, "error": str(exc)},
            level="warning",
            message="Ошибка запуска HTTP‑сервера healthcheck",
        )


async def main() -> None:
    """
    Главная функция приложения.
    """
    logger = get_logger(__name__)
    logger.info("Начало выполнения функции main()")
    try:
        # Инициализируем Sentry до старта всех остальных подсистем, чтобы
        # необработанные исключения в процессе инициализации также уходили
        # в систему мониторинга.
        _init_sentry(logger)

        # Запускаем HTTP‑экспортёр Prometheus до старта основного цикла бота,
        # чтобы метрики были доступны сразу после инициализации приложения.
        _start_prometheus_exporter(logger)

        # Поднимаем HTTP‑сервер healthcheck (/health) в том же event loop.
        _start_health_server(logger)

        runner = BotRunner()
        logger.info("BotRunner создан, запуск метода run()")
        await runner.run()
        logger.info("Функция main() завершена успешно")
    except Exception as e:
        # Любое необработанное исключение в main считаем критическим.
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(e)
        except Exception:
            # Ошибки интеграции Sentry не должны маскировать исходное
            # исключение.
            pass

        log_event(
            event="unhandled_exception",
            status="error",
            extra={"where": "main", "error": str(e)},
            level="error",
            message="Необработанное исключение в функции main()",
        )
        logger.error(f"Ошибка в функции main(): {e}", exc_info=True)
        raise


if __name__ == "__main__":
    """
    Точка входа в приложение.
    """
    logger = get_logger(__name__)
    logger.info("Запуск приложения из точки входа")
    try:
        # Запускаем главную функцию
        logger.info("Вызов asyncio.run(main())")
        asyncio.run(main())
        logger.info("Приложение завершено успешно")
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания (KeyboardInterrupt)")
        print("\n🛑 Получен сигнал прерывания. Завершение работы...")
    except Exception as e:
        # Финальная линия обороны: любое необработанное исключение здесь
        # означает аварийное завершение процесса.
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(e)
        except Exception:
            pass

        log_event(
            event="unhandled_exception",
            status="error",
            extra={"where": "__main__", "error": str(e)},
            level="critical",
            message="Критическая ошибка в точке входа приложения",
        )
        logger.error(f"Критическая ошибка в точке входа: {e}", exc_info=True)
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
