"""Unit of Work для управления транзакциями БД."""

from __future__ import annotations

import asyncpg

from infra.database.postgres_client import _get_postgres_pool
from shared.base.base_service import BaseService
from shared.protocols import ILogger


class DatabaseUnitOfWork(BaseService):
    """Unit of Work для управления транзакциями PostgreSQL.

    Группирует операции БД в одну транзакцию, обеспечивая атомарность
    и возможность отката при ошибках.

    Улучшения:
    - Более надёжная обработка ошибок в commit()/rollback()
    - Гарантированное освобождение соединения даже при ошибках
    - Проверка состояния транзакции перед операциями
    - Защита от повторного коммита/отката
    """

    def __init__(self, pool: asyncpg.Pool | None = None, *, logger: ILogger) -> None:
        """Инициализирует Unit of Work.

        Args:
            pool: Пул подключений PostgreSQL. Если не указан, используется глобальный пул.
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._pool = pool or _get_postgres_pool()  # Используем приватную функцию как fallback
        self._connection: asyncpg.Connection | None = None
        self._transaction: asyncpg.Transaction | None = None
        self._is_committed = False
        self._is_rolled_back = False

    async def __aenter__(self) -> DatabaseUnitOfWork:
        """Вход в контекстный менеджер. Начинает транзакцию."""
        await self.begin()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Выход из контекстного менеджера. Коммитит или откатывает транзакцию."""
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        except Exception as e:
            # Логируем ошибку, но гарантируем освобождение соединения
            self.logger.error(
                f"Ошибка при завершении транзакции: {e}",
                exc_info=True,
            )
            # Принудительно освобождаем соединение даже при ошибке
            await self._release()

    async def begin(self) -> None:
        """Начинает транзакцию."""
        if self._connection is not None:
            raise RuntimeError("Транзакция уже начата")

        try:
            self._connection = await self._pool.acquire()
            self._transaction = self._connection.transaction()
            await self._transaction.start()
            self._is_committed = False
            self._is_rolled_back = False
            self.logger.debug("Транзакция начата")
        except Exception as e:
            # Если не удалось начать транзакцию, освобождаем соединение
            if self._connection is not None:
                await self._pool.release(self._connection)
                self._connection = None
            raise RuntimeError(f"Не удалось начать транзакцию: {e}") from e

    async def commit(self) -> None:
        """Коммитит транзакцию."""
        if self._transaction is None:
            raise RuntimeError("Транзакция не начата")

        if self._is_committed:
            self.logger.warning("Попытка повторного коммита транзакции, игнорируем")
            return

        if self._is_rolled_back:
            raise RuntimeError("Нельзя коммитить уже откатанную транзакцию")

        try:
            await self._transaction.commit()
            self._is_committed = True
            self.logger.debug("Транзакция закоммичена")
        except Exception as e:
            self.logger.error(f"Ошибка при коммите транзакции: {e}", exc_info=True)
            # Пытаемся откатить при ошибке коммита
            try:
                await self._transaction.rollback()
                self._is_rolled_back = True
            except Exception as rollback_error:
                self.logger.error(
                    f"Ошибка при откате после неудачного коммита: {rollback_error}",
                    exc_info=True,
                )
            raise
        finally:
            # Гарантируем освобождение соединения даже при ошибке коммита
            await self._release()

    async def rollback(self) -> None:
        """Откатывает транзакцию."""
        if self._transaction is None:
            # Если транзакция не начата, просто освобождаем ресурсы
            await self._release()
            return

        if self._is_rolled_back:
            self.logger.warning("Попытка повторного отката транзакции, игнорируем")
            await self._release()
            return

        if self._is_committed:
            raise RuntimeError("Нельзя откатывать уже закоммиченную транзакцию")

        try:
            await self._transaction.rollback()
            self._is_rolled_back = True
            self.logger.debug("Транзакция откачена")
        except Exception as e:
            self.logger.error(f"Ошибка при откате транзакции: {e}", exc_info=True)
            # Продолжаем освобождение ресурсов даже при ошибке отката
        finally:
            # Гарантируем освобождение соединения даже при ошибке отката
            await self._release()

    async def _release(self) -> None:
        """Освобождает соединение.

        Гарантирует освобождение соединения даже при ошибках.
        """
        if self._connection is not None:
            try:
                await self._pool.release(self._connection)
            except Exception as e:
                # Логируем, но не пробрасываем - соединение может быть уже освобождено
                self.logger.warning(f"Ошибка при освобождении соединения: {e}")
            finally:
                self._connection = None
                self._transaction = None

    @property
    def connection(self) -> asyncpg.Connection:
        """Возвращает соединение БД для использования в репозиториях.

        Returns:
            Соединение БД, используемое в текущей транзакции.

        Raises:
            RuntimeError: Если транзакция не начата.
        """
        if self._connection is None:
            raise RuntimeError("Транзакция не начата. Вызовите begin() или используйте async with")
        return self._connection

    def get_connection(self) -> asyncpg.Connection | None:
        """Возвращает соединение БД или None, если транзакция не начата.

        Используется репозиториями для получения опционального соединения.

        Returns:
            Соединение БД или None.
        """
        return self._connection
