"""Main application entrypoint.

Creates Config and Container instance,
starts aiogram bot and prometheus http server.
"""

import asyncio

from aiogram import Bot, Dispatcher

from infra.config import Config
from infra.di import Container
from presentation.aiogram import POLLING_ALLOWED_UPDATES, is_telegram_retryable, setup_bot, setup_dp


async def main() -> None:
    # 1. Configuration
    config = Config()

    # 2. DI
    container = Container(config=config)
    logger = container.observe.logger.bind(module=__name__)
    metrics = container.observe.metrics

    # 3. Delivery
    logger.debug("Building aiogram bot...")

    rl = container.resilience.rate_limiter(
        config=config.telegram.rate_limit,
    )
    retrier = container.resilience.retry(
        config=config.telegram.retry,
        predicate=is_telegram_retryable,
    )

    bot = Bot(token=config.telegram.token.get_secret_value())
    setup_bot(
        bot=bot,
        rate_limiter=rl,
        retrier=retrier,
        logger=container.observe.logger,
    )

    logger.debug("Building aiogram dispatcher...")

    dp = Dispatcher()
    setup_dp(
        dp=dp,
        scope_factory=container.get_scope,
        rate_limiter=rl,
        admin_id=config.telegram.admin_id,
        logger=container.observe.logger,
    )

    try:
        metrics.serve()
        await dp.start_polling(bot, allowed_updates=POLLING_ALLOWED_UPDATES)

    except Exception:
        logger.exception("Unexpected runtime error. Shutting down...")
        raise

    finally:
        await bot.session.close()
        await container.shutdown()
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
