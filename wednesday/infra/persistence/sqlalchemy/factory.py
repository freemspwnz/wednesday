from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from app.protocols import Logger
from infra.config import PostgresConfig

_SQLA_CLOSE_TIMEOUT = 5.0


def create_engine(config: PostgresConfig, logger: Logger) -> AsyncEngine:
    """Create AsyncEngine for PostgreSQL via SQLAlchemy."""
    logger.debug("Creating PostgreSQL engine...")
    engine = create_async_engine(
        url=config.dsn,
        pool_pre_ping=config.pool_pre_ping,
        echo=config.echo,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
    )
    logger.debug("PostgreSQL engine created successfully.")
    return engine


async def close_engine(
    *,
    engine: AsyncEngine,
    logger: Logger,
) -> None:
    """Close AsyncEngine."""
    logger.debug("Closing PostgreSQL engine...")
    try:
        async with asyncio.timeout(_SQLA_CLOSE_TIMEOUT):
            await engine.dispose()
    except TimeoutError:
        logger.warning("PostgreSQL engine dispose timed out. Forced exit.")
    except Exception as e:
        logger.error(f"Non-critical error during engine dispose: {e}", exc_info=True)
    logger.info("PostgreSQL engine closed successfully.")
