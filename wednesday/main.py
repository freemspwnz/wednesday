"""Main application entrypoint.

Creates Config and Container instance,
starts aiogram bot and prometheus http server.
"""

import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher

from infra.config import Config
from infra.di import Container
from presentation.aiogram import POLLING_ALLOWED_UPDATES, is_telegram_retryable, setup_bot, setup_dp
from presentation.aiogram.scheduler import CatalogScheduleRunner


async def main() -> None:
    # 1. Configuration
    config = Config()

    # 2. DI
    container = Container(config=config)
    logger = container.observe.logger.bind(module=__name__)
    metrics = container.observe.metrics

    # 3. Delivery
    logger.debug("Building aiogram bot...")

    limiter = container.resilience.limiter(
        config=config.telegram.limiter,
    )
    retrier = container.resilience.retrier(
        config=config.telegram.retrier,
        predicate=is_telegram_retryable,
    )

    bot = Bot(token=config.telegram.token.get_secret_value())
    setup_bot(
        bot=bot,
        limiter=limiter,
        retrier=retrier,
        logger=container.observe.logger,
    )

    logger.debug("Building aiogram dispatcher...")

    dp = Dispatcher()
    setup_dp(
        dp=dp,
        scope=container.scope,
        limiter=limiter,
        admin_id=config.telegram.admin_id,
        logger=container.observe.logger,
    )

    try:
        await container.persistence.warmup()
        metrics.serve()
        runner = CatalogScheduleRunner(
            bot=bot,
            scope=container.scope,
            logger=container.observe.logger,
        )
        runner_task = asyncio.create_task(runner.run(), name="catalog-schedule")
        try:
            await dp.start_polling(bot, allowed_updates=POLLING_ALLOWED_UPDATES)
        finally:
            runner_task.cancel()
            with suppress(asyncio.CancelledError):
                await runner_task

    except Exception:
        logger.exception("Unexpected runtime error. Shutting down...")
        raise

    finally:
        await bot.session.close()
        await container.shutdown()
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
