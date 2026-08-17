import asyncio
from functools import cached_property

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import ExceptionContext
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.exceptions import DBUnavailableError
from app.protocols import DBMetrics, Logger, UoW, UoWFactory
from infra.config import PostgresConfig

from .uow import SQLAUoW

_SQLA_CLOSE_TIMEOUT = 5.0


class SQLAUoWFactory(UoWFactory):
    """Creates ``SQLAUoW`` instances backed by a shared async engine."""

    def __init__(self, *, config: PostgresConfig, metrics: DBMetrics, logger: Logger) -> None:
        self._config = config
        self._metrics = metrics
        self._logger = logger.bind(module=self.__class__.__name__)

    def __call__(self) -> UoW:
        return SQLAUoW(self._sessionmaker)

    async def warmup(self) -> None:
        """Open a connection and run ``SELECT 1`` so boot fails if Postgres is down."""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError, TimeoutError) as e:
            self._logger.error("Database is not available.", exc_info=True)
            raise DBUnavailableError("Database is not available.") from e

    async def aclose(self) -> None:
        self._logger.debug("Closing SQLAlchemy async engine...")
        try:
            async with asyncio.timeout(_SQLA_CLOSE_TIMEOUT):
                await self._engine.dispose()
        except TimeoutError:
            self._logger.warning("SQLAlchemy engine dispose timed out. Forced exit.")
        except Exception as e:
            self._logger.error(f"Non-critical error during engine dispose: {e}", exc_info=True)
        self._logger.info("SQLAlchemy engine closed successfully.")

    @cached_property
    def _sessionmaker(self) -> async_sessionmaker:
        return async_sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @cached_property
    def _engine(self) -> AsyncEngine:
        self._logger.debug("Creating SQLAlchemy async engine...")
        engine = create_async_engine(
            url=self._config.dsn,
            pool_pre_ping=self._config.pool_pre_ping,
            echo=self._config.echo,
            pool_size=self._config.pool_size,
            max_overflow=self._config.max_overflow,
        )
        self._attach_engine_metrics(engine.sync_engine, self._metrics)
        self._logger.debug("SQLAlchemy engine created successfully.")
        return engine

    @staticmethod
    def _attach_engine_metrics(engine: Engine, metrics: DBMetrics) -> None:
        def handle_error(exception_context: ExceptionContext) -> None:
            metrics.on_cursor_error(
                statement=exception_context.statement or "",
                error_type=type(exception_context.original_exception).__name__,
                context=getattr(exception_context, "execution_context", None),
            )

        event.listen(engine, "before_cursor_execute", metrics.on_before_cursor_execute)
        event.listen(engine, "after_cursor_execute", metrics.on_after_cursor_execute)
        event.listen(engine, "handle_error", handle_error)
