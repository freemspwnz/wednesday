from __future__ import annotations

import asyncio

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import ExceptionContext
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.protocols import DBMetrics, Logger
from infra.config import PostgresConfig

_SQLA_CLOSE_TIMEOUT = 5.0


def _attach_engine_metrics(engine: Engine, metrics: DBMetrics) -> None:
    def before_cursor_execute(  # noqa: PLR0913, PLR0917
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        metrics.on_before_cursor_execute(context=context, statement=statement)

    def after_cursor_execute(  # noqa: PLR0913, PLR0917
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        metrics.on_after_cursor_execute(context=context, statement=statement)

    def handle_error(exception_context: ExceptionContext) -> None:
        metrics.on_cursor_error(
            statement=exception_context.statement or "",
            error_type=type(exception_context.original_exception).__name__,
            context=getattr(exception_context, "execution_context", None),
        )

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine, "handle_error", handle_error)


def create_engine(
    *,
    config: PostgresConfig,
    metrics: DBMetrics,
    logger: Logger,
) -> AsyncEngine:
    """Create AsyncEngine for PostgreSQL via SQLAlchemy."""
    logger.debug("Creating PostgreSQL engine...")
    engine = create_async_engine(
        url=config.dsn,
        pool_pre_ping=config.pool_pre_ping,
        echo=config.echo,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
    )
    _attach_engine_metrics(engine.sync_engine, metrics)
    logger.debug("PostgreSQL engine created successfully.")
    return engine


async def close_engine(*, engine: AsyncEngine, logger: Logger) -> None:
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
