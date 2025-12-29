"""
Чистая точка входа (Composition Root) для Wednesday Frog Bot.
Оптимизировано для работы на сервере с 1 ГБ RAM.

Управляет только ресурсами: PostgresPool, Redis, aiohttp, Celery.
Логика бота вынесена в WednesdayBot.
"""

import asyncio
import ssl
from pathlib import Path

import aiohttp
from telegram.ext import ApplicationBuilder

from bot.new_wednesday_bot import WednesdayBot
from infra.celery.app import celery_app
from infra.celery.celery_task_queue import CeleryTaskQueue
from infra.database.postgres_client import PostgresPoolFactory
from infra.database.postgres_schema import ensure_schema
from infra.logging.logger import get_logger
from infra.metrics.metrics import Metrics
from infra.new_container import Container
from infra.redis.redis_client import RedisClient, RedisClientFactory
from shared.config import Config


async def main() -> None:
    """Главная функция приложения - Composition Root.

    Управляет только ресурсами:
    - PostgresPool (max_size=5 для экономии памяти)
    - RedisClient
    - aiohttp.ClientSession
    - CeleryTaskQueue

    Логика бота вынесена в WednesdayBot.
    """
    main_logger = get_logger("main")
    main_logger.info(
        "Запуск Wednesday Frog Bot",
        event="main_start",
        status="started",
    )

    # 1. Конфиг
    main_logger.debug(
        "Загрузка конфигурации",
        event="main_load_config",
        status="started",
    )
    config = Config()
    main_logger.info(
        "Конфигурация загружена",
        event="main_config_loaded",
        status="ok",
    )

    # 2. Создание Telegram Application ПЕРЕД созданием контейнера
    main_logger.debug(
        "Создание Telegram Application",
        event="main_create_telegram_app",
        status="started",
    )
    bot_token = config.telegram.bot_token
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN должен быть установлен. Проверьте конфигурацию.")
    application = ApplicationBuilder().token(bot_token).build()
    bot_instance = application.bot
    main_logger.info(
        "Telegram Application создано",
        event="main_telegram_app_ready",
        status="ok",
    )

    # 3. Инициализация ресурсов
    # 3.1. PostgresPool
    main_logger.debug(
        "Инициализация Postgres pool",
        event="main_init_postgres",
        status="started",
    )
    pool_factory = PostgresPoolFactory(config=config)
    db_pool = await pool_factory.get_pool(min_size=1, max_size=5)
    main_logger.info(
        "Postgres pool создан",
        event="main_postgres_pool_ready",
        status="ok",
        max_size=5,
    )

    # Валидация схемы БД
    main_logger.debug(
        "Валидация схемы БД",
        event="main_validate_schema",
        status="started",
    )
    await ensure_schema(pool=db_pool)
    main_logger.debug(
        "Схема БД валидирована",
        event="main_schema_validated",
        status="ok",
    )

    # 3.2. RedisClient
    main_logger.debug(
        "Инициализация Redis клиента",
        event="main_init_redis",
        status="started",
    )
    redis_factory = RedisClientFactory(config=config)
    url = config.redis.url
    if url:
        redis_client = await redis_factory.get_client(url=url)
    else:
        redis_client = await redis_factory.get_client(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password,
        )
    main_logger.info(
        "Redis клиент создан",
        event="main_redis_client_ready",
        status="ok",
    )

    # 3.3. HTTP Session (с async with для гарантированного закрытия)
    main_logger.debug(
        "Настройка HTTP сессии",
        event="main_setup_http_session",
        status="started",
    )
    max_timeout = max(
        config.kandinsky.generation_timeout.total_seconds(),
        config.gigachat.prompt_timeout.total_seconds(),
    )
    http_timeout = aiohttp.ClientTimeout(
        total=max_timeout,
        connect=30,
    )

    ssl_context = True
    if isinstance(config.gigachat.verify_ssl, bool):
        ssl_context = config.gigachat.verify_ssl
    elif isinstance(config.gigachat.verify_ssl, str):
        cert_path = Path(config.gigachat.verify_ssl)
        if cert_path.exists():
            ssl_context = ssl.create_default_context(cafile=str(cert_path))
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    # 3.4. CeleryTaskQueue
    main_logger.debug(
        "Создание CeleryTaskQueue",
        event="main_create_task_queue",
        status="started",
    )
    task_queue = CeleryTaskQueue(celery_app_instance=celery_app)
    main_logger.debug(
        "CeleryTaskQueue создан",
        event="main_task_queue_created",
        status="ok",
    )

    # 4. Metrics service
    main_logger.debug(
        "Создание Metrics service",
        event="main_create_metrics",
        status="started",
    )
    metrics_service = Metrics(
        pool=db_pool,
        logger=main_logger.bind(module="metrics_service"),
        redis_factory=redis_factory,
    )
    main_logger.debug(
        "Metrics service создан",
        event="main_metrics_created",
        status="ok",
    )

    # 5. Composition Root: создание Container и WednesdayBot
    try:
        async with aiohttp.ClientSession(timeout=http_timeout, connector=connector) as http_session:
            main_logger.info(
                "HTTP сессия создана",
                event="main_http_session_ready",
                status="ok",
                timeout_total=max_timeout,
            )

            # Создание Container с передачей всех ресурсов
            main_logger.debug(
                "Создание Container",
                event="main_create_container",
                status="started",
            )
            container = Container(
                config=config,
                logger=main_logger.bind(module="container"),
                db_pool=db_pool,
                redis_client=redis_client,
                bot_client=bot_instance,
                metrics_service=metrics_service,
                task_queue=task_queue,
                http_session=http_session,
            )
            main_logger.info(
                "Container создан и готов",
                event="main_container_ready",
                status="ok",
            )

            # Создание WednesdayBot
            main_logger.debug(
                "Создание WednesdayBot",
                event="main_create_bot",
                status="started",
            )
            bot_app = WednesdayBot(
                application=application,
                container=container,
                logger=main_logger.bind(module="WednesdayBot"),
            )
            main_logger.info(
                "WednesdayBot создан",
                event="main_bot_created",
                status="ok",
            )

            # Запуск бота
            main_logger.info(
                "Запуск бота",
                event="main_start_bot",
                status="started",
            )
            await bot_app.run()
    finally:
        # Cleanup: закрытие ресурсов
        main_logger.info(
            "Завершение работы, закрытие ресурсов",
            event="main_shutdown_start",
            status="started",
        )

        # HTTP сессия закрывается автоматически через async with

        # Закрываем фабрики (они закроют пулы и клиенты)
        main_logger.debug(
            "Закрытие Postgres pool",
            event="main_close_postgres",
            status="started",
        )
        await pool_factory.close()
        main_logger.info(
            "Postgres pool закрыт",
            event="main_postgres_closed",
            status="ok",
        )

        main_logger.debug(
            "Закрытие Redis клиента",
            event="main_close_redis",
            status="started",
        )
        await redis_factory.close()
        main_logger.info(
            "Redis клиент закрыт",
            event="main_redis_closed",
            status="ok",
        )

        main_logger.info(
            "Все ресурсы закрыты, приложение остановлено",
            event="main_shutdown_complete",
            status="ok",
        )


if __name__ == "__main__":
    asyncio.run(main())

