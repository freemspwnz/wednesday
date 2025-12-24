"""Application service для проверки прав администратора."""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.base.exceptions import AccessDeniedError
from shared.protocols import IAdminsRepo, ILogger


class AdminAccessService(BaseService):
    """Сервис для проверки прав администратора.

    Инкапсулирует логику проверки прав администратора и главного администратора,
    предоставляя единый интерфейс для всех компонентов приложения.
    """

    def __init__(
        self,
        admins_repo: IAdminsRepo,
        super_admin_id: int | None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис проверки прав.

        Args:
            admins_repo: Репозиторий администраторов.
            super_admin_id: ID главного администратора (из .env).
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._admins_repo = admins_repo
        self._super_admin_id = super_admin_id

    async def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором.

        Args:
            user_id: ID пользователя для проверки.

        Returns:
            True если пользователь является администратором, False иначе.
        """
        return await self._admins_repo.is_admin(user_id)

    async def is_super_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь главным администратором.

        Args:
            user_id: ID пользователя для проверки.

        Returns:
            True если пользователь является главным администратором, False иначе.
        """
        if self._super_admin_id is None:
            return False
        return int(user_id) == int(self._super_admin_id)

    async def require_admin(self, user_id: int) -> None:
        """Требует, чтобы пользователь был администратором.

        Args:
            user_id: ID пользователя для проверки.

        Raises:
            AccessDeniedError: Если пользователь не является администратором.
        """
        if not await self.is_admin(user_id):
            raise AccessDeniedError(f"Пользователь {user_id} не является администратором")

    async def require_super_admin(self, user_id: int) -> None:
        """Требует, чтобы пользователь был главным администратором.

        Args:
            user_id: ID пользователя для проверки.

        Raises:
            AccessDeniedError: Если пользователь не является главным администратором.
        """
        if not await self.is_super_admin(user_id):
            raise AccessDeniedError(f"Пользователь {user_id} не является главным администратором")

    async def list_all_admins(self) -> list[int]:
        """Возвращает список всех администраторов.

        Returns:
            Список ID всех администраторов.
        """
        return await self._admins_repo.list_all_admins()
