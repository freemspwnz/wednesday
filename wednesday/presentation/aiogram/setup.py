from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramAPIError

from app.protocols import Logger, RateLimiter, Retrier, ScopeFactory

from .filters import AdminAccessFilter
from .messages import common as common_msg, system as system_msg
from .middlewares import (
    DIMiddleware,
    RateLimitRequestMW,
    RegistrationMiddleware,
    RetryRequestMW,
    ThrottlingMiddleware,
)
from .routers import (
    chat_router,
    common_router,
    error_handler,
    image_router,
    user_router,
)
from .routers.user import admin_router

POLLING_ALLOWED_UPDATES: list[str] = [
    "message",
    "callback_query",
    "my_chat_member",
    "chat_member",
]


def setup_bot(
    bot: Bot,
    limiter: RateLimiter,
    retrier: Retrier,
    logger: Logger,
) -> None:
    """Modify bot session to fit telegram API limits."""

    log = logger.bind(module="Bot")
    log.info("Setting up bot...")

    bot.session.middleware(
        RetryRequestMW(
            retrier=retrier,
            logger=logger,
        ),
    )

    bot.session.middleware(
        RateLimitRequestMW(
            limiter=limiter,
            logger=logger,
        ),
    )


def setup_dp(
    dp: Dispatcher,
    scope_factory: ScopeFactory,
    limiter: RateLimiter,
    admin_id: int,
    logger: Logger,
) -> None:
    """Setup dispatcher middleware.

    On an incoming update, the first registered ``dp.update.middleware`` runs first.
    Register outer-to-inner: DI → Registration → Throttling → handler.
    """

    log = logger.bind(module="Dispatcher")
    log.info("Setting up dispatcher...")

    setup_routers(logger=logger)

    dp.include_router(build_root_router())

    di_mw = DIMiddleware(scope_factory=scope_factory, logger=logger)

    dp.errors.register(error_handler)
    dp.errors.middleware(di_mw)

    dp.update.middleware(di_mw)
    dp.update.middleware(RegistrationMiddleware(logger=logger))
    dp.update.middleware(ThrottlingMiddleware(limiter=limiter, logger=logger))

    @dp.startup()
    async def dp_startup(bot: Bot) -> None:
        su_logger = log.bind(event="startup")
        try:
            await bot.set_my_commands(list(common_msg.BOT_COMMANDS))
        except TelegramAPIError as exc:
            su_logger.error(
                "Failed to set bot commands menu",
                error=str(exc),
                exc_info=True,
            )
        try:
            await bot.send_message(chat_id=admin_id, text=system_msg.BOT_STARTED)
        except TelegramAPIError as exc:
            su_logger.error(
                "Failed to send startup message to admin",
                admin_id=admin_id,
                error=str(exc),
                exc_info=True,
            )

    @dp.shutdown()
    async def dp_shutdown(bot: Bot) -> None:
        sd_logger = log.bind(event="shutdown")
        try:
            await bot.send_message(chat_id=admin_id, text=system_msg.BOT_STOPPED)
        except TelegramAPIError as exc:
            sd_logger.error(
                "Failed to send shutdown message to admin",
                admin_id=admin_id,
                error=str(exc),
                exc_info=True,
            )


def build_root_router() -> Router:
    root_router = Router(name="root")

    root_router.include_router(chat_router)
    root_router.include_router(image_router)
    root_router.include_router(user_router)
    root_router.include_router(common_router)

    return root_router


def setup_routers(*, logger: Logger) -> None:
    """Attach router-level filters."""

    log = logger.bind(module="Router")
    log.info("Setting up routers")

    admin_router.message.filter(AdminAccessFilter(logger=logger))
