"""Application service для координации админских команд."""

from __future__ import annotations

from dataclasses import dataclass

from app.admin_access_service import AdminAccessService
from shared.base.base_service import BaseService
from shared.base.exceptions import RepoError, ServiceError
from shared.protocols import IAdminsRepo, IChatsRepo, ILogger, IUsageTracker


@dataclass
class CommandResult:
    """Результат выполнения админской команды."""

    success: bool
    message: str


@dataclass
class ChatInfo:
    """Информация о чате."""

    chat_id: int
    title: str | None = None


class AdminCommandService(BaseService):
    """Сервис для координации админских команд.

    Инкапсулирует бизнес-логику выполнения админских команд,
    обеспечивая единый интерфейс и соблюдение границ слоёв.
    """

    def __init__(
        self,
        *,
        chats: IChatsRepo | None,
        usage: IUsageTracker | None,
        admins_repo: IAdminsRepo,
        admin_access_service: AdminAccessService,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис админских команд.

        Args:
            chats: Репозиторий чатов (опционально).
            usage: Трекер использования (опционально).
            admins_repo: Репозиторий администраторов.
            admin_access_service: Сервис проверки прав администратора.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._chats = chats
        self._usage = usage
        self._admins_repo = admins_repo
        self._admin_access = admin_access_service

    async def add_chat(
        self,
        chat_id: int,
        source: str = "Manually added",
    ) -> CommandResult:
        """Добавляет чат в список рассылки.

        Args:
            chat_id: ID чата для добавления.
            source: Источник добавления (опционально).

        Returns:
            Результат выполнения команды.

        Raises:
            AccessDeniedError: Если пользователь не является администратором.
            ServiceError: Если репозиторий чатов не инициализирован.
        """
        if self._chats is None:
            raise ServiceError("Репозиторий чатов не инициализирован")

        try:
            await self._chats.add_chat(chat_id, source)
            return CommandResult(
                success=True,
                message=f"✅ Чат {chat_id} добавлен в рассылку",
            )
        except RepoError as e:
            self.logger.error(
                f"Ошибка при добавлении чата {chat_id}: {e}",
                event="add_chat_error",
                status="error",
                chat_id=chat_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при добавлении чата: {str(e)[:200]}",
            )

    async def remove_chat(
        self,
        chat_id: int,
    ) -> CommandResult:
        """Удаляет чат из списка рассылки.

        Args:
            chat_id: ID чата для удаления.

        Returns:
            Результат выполнения команды.

        Raises:
            ServiceError: Если репозиторий чатов не инициализирован.
        """
        if self._chats is None:
            raise ServiceError("Репозиторий чатов не инициализирован")

        try:
            await self._chats.remove_chat(chat_id)
            return CommandResult(
                success=True,
                message=f"✅ Чат {chat_id} удалён из рассылки",
            )
        except RepoError as e:
            self.logger.error(
                f"Ошибка при удалении чата {chat_id}: {e}",
                event="remove_chat_error",
                status="error",
                chat_id=chat_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при удалении чата: {str(e)[:200]}",
            )

    async def list_chat_ids(self) -> list[int]:
        """Возвращает список ID всех активных чатов.

        Returns:
            Список ID чатов.

        Raises:
            ServiceError: Если репозиторий чатов не инициализирован.
        """
        if self._chats is None:
            raise ServiceError("Репозиторий чатов не инициализирован")

        try:
            return await self._chats.list_chat_ids()
        except RepoError as e:
            self.logger.error(
                f"Ошибка при получении списка чатов: {e}",
                event="list_chats_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise ServiceError(f"Не удалось получить список чатов: {e}") from e

    async def set_frog_threshold(
        self,
        threshold: int,
        max_threshold: int = 100,
    ) -> CommandResult:
        """Устанавливает порог ручных генераций /frog.

        Args:
            threshold: Новый порог (будет ограничен max_threshold).
            max_threshold: Максимально допустимый порог.

        Returns:
            Результат выполнения команды с информацией о текущем использовании.

        Raises:
            ServiceError: Если трекер использования не инициализирован.
            ValueError: Если threshold <= 0.
        """
        if self._usage is None:
            raise ServiceError("Трекер использования не инициализирован")

        if threshold <= 0:
            raise ValueError(f"Порог должен быть положительным числом, получено: {threshold}")

        # Ограничиваем максимумом
        desired = min(threshold, max_threshold)

        try:
            new_threshold = await self._usage.set_frog_threshold(desired)
            total, _threshold, quota = await self._usage.get_limits_info()

            return CommandResult(
                success=True,
                message=f"✅ Порог /frog установлен: {new_threshold} (текущее использование: {total}/{quota})",
            )
        except (RepoError, ServiceError) as e:
            self.logger.error(
                f"Ошибка при установке порога /frog: {e}",
                event="set_frog_threshold_error",
                status="error",
                threshold=desired,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при установке порога: {str(e)[:200]}",
            )

    async def set_frog_used(
        self,
        count: int,
    ) -> CommandResult:
        """Устанавливает текущее значение выработки /frog за месяц.

        Args:
            count: Количество использований (будет ограничено квотой).

        Returns:
            Результат выполнения команды с информацией о лимитах.

        Raises:
            ServiceError: Если трекер использования не инициализирован.
            ValueError: Если count < 0.
        """
        if self._usage is None:
            raise ServiceError("Трекер использования не инициализирован")

        if count < 0:
            raise ValueError(f"Количество использований должно быть неотрицательным, получено: {count}")

        try:
            # Ограничиваем значением квоты
            capped = min(count, self._usage.monthly_quota)
            await self._usage.set_month_total(capped)
            total, threshold, quota = await self._usage.get_limits_info()

            return CommandResult(
                success=True,
                message=f"✅ Текущее использование /frog: {total}/{threshold} (квота: {quota})",
            )
        except (RepoError, ServiceError) as e:
            self.logger.error(
                f"Ошибка при установке использованного количества /frog: {e}",
                event="set_frog_used_error",
                status="error",
                count=count,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при установке использованного количества: {str(e)[:200]}",
            )

    async def add_admin(
        self,
        target_user_id: int,
        requester_user_id: int,
    ) -> CommandResult:
        """Добавляет администратора.

        Args:
            target_user_id: ID пользователя для добавления в администраторы.
            requester_user_id: ID пользователя, запрашивающего операцию.

        Returns:
            Результат выполнения команды.

        Raises:
            AccessDeniedError: Если запрашивающий не является главным администратором.
        """
        # Проверяем права
        await self._admin_access.require_super_admin(requester_user_id)

        try:
            success = await self._admins_repo.add_admin(target_user_id)
            if success:
                return CommandResult(
                    success=True,
                    message=f"✅ Пользователь {target_user_id} получил админ‑права",
                )
            return CommandResult(
                success=True,
                message=f"ℹ️ Пользователь {target_user_id} уже является администратором",
            )
        except RepoError as e:
            self.logger.error(
                f"Ошибка при добавлении администратора {target_user_id}: {e}",
                event="add_admin_error",
                status="error",
                target_user_id=target_user_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при добавлении администратора: {str(e)[:200]}",
            )

    async def remove_admin(
        self,
        target_user_id: int,
        requester_user_id: int,
        super_admin_id: int | None,
    ) -> CommandResult:
        """Удаляет администратора.

        Args:
            target_user_id: ID пользователя для удаления из администраторов.
            requester_user_id: ID пользователя, запрашивающего операцию.
            super_admin_id: ID главного администратора (нельзя удалить).

        Returns:
            Результат выполнения команды.

        Raises:
            AccessDeniedError: Если запрашивающий не является главным администратором.
            ServiceError: Если пытаются удалить главного администратора.
        """
        # Проверяем права
        await self._admin_access.require_super_admin(requester_user_id)

        # Проверяем, не пытаются ли удалить главного админа
        if super_admin_id and int(target_user_id) == int(super_admin_id):
            raise ServiceError("Нельзя удалить главного администратора (из .env)")

        try:
            success = await self._admins_repo.remove_admin(target_user_id)
            if success:
                return CommandResult(
                    success=True,
                    message=f"✅ У пользователя {target_user_id} удалены админ‑права",
                )
            return CommandResult(
                success=True,
                message=f"ℹ️ Пользователь {target_user_id} не является администратором",
            )
        except RepoError as e:
            self.logger.error(
                f"Ошибка при удалении администратора {target_user_id}: {e}",
                event="remove_admin_error",
                status="error",
                target_user_id=target_user_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при удалении администратора: {str(e)[:200]}",
            )

    async def list_all_admins(self) -> list[int]:
        """Возвращает список всех администраторов.

        Returns:
            Список ID всех администраторов.
        """
        return await self._admin_access.list_all_admins()
