import asyncio
import logging
import sys
from types import TracebackType
from typing import Any

from loguru import logger

from infra.config import LoggingConfig

from .formatters import LoguruHandler, scrub


def _sys_exception_handler(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("Uncaught exception")


def _asyncio_exception_handler(
    loop: asyncio.AbstractEventLoop,
    context: dict[str, object],
) -> None:
    msg = context.get("message", "")
    exc = context.get("exception")
    if isinstance(exc, BaseException):
        logger.opt(exception=exc).error("asyncio: {}", msg)
    else:
        logger.error("asyncio: {} | context={}", msg, context)


def setup_logging(
    config: LoggingConfig,
    env: str,
    version: str,
    secrets: list[str],
) -> None:
    def patch_record(record: Any) -> None:  # noqa: ANN401
        # Mask message
        record["message"] = scrub(record["message"], secrets=secrets)
        # Mask extra data
        record["extra"] = scrub(record["extra"], secrets=secrets)

    # 1. Cleanup
    logger.remove()

    logger.configure(
        patcher=patch_record,
        extra={
            "service": "wednesday",
            "env": env,
            "version": version,
        },
    )

    # 2. Configure console output
    logger.add(sys.stdout, level=config.level, serialize=config.serialize, format=config.format)

    # 3. File logging
    if config.to_file:
        logger.add(
            config.file_path,
            rotation="10 MB",
            retention="30 days",
            level=config.level,
            serialize=config.serialize,
            format=config.format,
        )

    # 4. Catch critical errors of Python and asyncio
    sys.excepthook = _sys_exception_handler
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.set_exception_handler(_asyncio_exception_handler)

    # 5. Catch standard logging
    logging.basicConfig(handlers=[LoguruHandler()], level=logging.NOTSET, force=True)

    # 6. Silence noisy libraries
    for name in config.noisy_libs:
        logging.getLogger(name).setLevel(logging.WARNING)

    logger.info(f"Logging configured (ENV={env}, LEVEL={config.level})")
