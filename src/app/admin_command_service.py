"""Application service для координации админских команд."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.admin_access_service import AdminAccessService
from shared.base.base_service import BaseService
from shared.base.exceptions import RepoError, ServiceError
from shared.protocols.infrastructure import ILogger
from shared.protocols.repositories import IAdminsRepo, IChatsRepo, IUsageTracker

if TYPE_CHECKING:
    from app.admin_notification_builders import AdminNotificationBuilders
    from app.chat_info_service import ChatInfoService
    from app.dispatch_delivery_service import DispatchDeliveryService
    from app.frog_limit_service import FrogRateLimiterService
    from app.image_service import ImageService


@dataclass
class CommandResult:
    """Результат выполнения админской команды.

    Использует dataclass для мутабельной структуры данных.
    Стандарт: Dataclass для мутабельных DTO, TypedDict для неизменяемых структур.
    """

    success: bool
    message: str


@dataclass
class ChatInfo:
    """Информация о чате.

    Использует dataclass для мутабельной структуры данных.
    Стандарт: Dataclass для мутабельных DTO, TypedDict для неизменяемых структур.
    """

    chat_id: int
    title: str | None = None


@dataclass
class ValidationResult:
    """Результат валидации.

    Использует dataclass для мутабельной структуры данных.
    """

    is_valid: bool
    error_message: str | None = None


class AdminCommandService(BaseService):
    """Сервис для координации админских команд.

    Инкапсулирует бизнес-логику выполнения админских команд,
    обеспечивая единый интерфейс и соблюдение границ слоёв.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        chats: IChatsRepo | None,
        usage: IUsageTracker | None,
        admins_repo: IAdminsRepo,
        admin_access_service: AdminAccessService,
        logger: ILogger,
        # Опциональные зависимости для расширенной функциональности
        image_service: ImageService | None = None,
        frog_limit_service: FrogRateLimiterService | None = None,
        dispatch_delivery_service: DispatchDeliveryService | None = None,
        chat_info_service: ChatInfoService | None = None,
        notification_builders: AdminNotificationBuilders | None = None,
    ) -> None:
        """Инициализирует сервис админских команд.

        Args:
            chats: Репозиторий чатов (опционально).
            usage: Трекер использования (опционально).
            admins_repo: Репозиторий администраторов.
            admin_access_service: Сервис проверки прав администратора.
            logger: Экземпляр логгера.
            image_service: Сервис генерации изображений (опционально, для force_send).
            frog_limit_service: Сервис проверки лимитов (опционально, для force_send).
            dispatch_delivery_service: Сервис отправки изображений (опционально, для force_send).
            chat_info_service: Сервис получения информации о чатах (опционально).
            notification_builders: Билдеры уведомлений (опционально, для форматирования).
        """
        super().__init__(logger)
        self._chats = chats
        self._usage = usage
        self._admins_repo = admins_repo
        self._admin_access = admin_access_service
        self._image_service = image_service
        self._frog_limit_service = frog_limit_service
        self._dispatch_delivery_service = dispatch_delivery_service
        self._chat_info_service = chat_info_service
        self._notification_builders = notification_builders

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

    @staticmethod
    def validate_chat_id(chat_id: int) -> ValidationResult:
        """Валидирует chat_id.

        Проверяет диапазон значений и другие ограничения.

        Args:
            chat_id: ID чата для валидации.

        Returns:
            Результат валидации с сообщением об ошибке при необходимости.
        """
        # Валидация диапазона: Telegram chat_id может быть положительным (пользователи)
        # или отрицательным (группы/каналы, начинаются с -100)
        # Максимальное значение для int64: 2**63 - 1, минимальное: -2**63
        if chat_id < -(2**63) or chat_id > 2**63 - 1:
            return ValidationResult(
                is_valid=False,
                error_message="chat_id выходит за допустимый диапазон",
            )
        if chat_id == 0:
            return ValidationResult(
                is_valid=False,
                error_message="chat_id не может быть нулем",
            )
        return ValidationResult(is_valid=True)

    @staticmethod
    def determine_target_chats(
        chat_ids: list[int],
        arg: str,
    ) -> list[int]:
        """Определяет целевые чаты на основе аргумента команды.

        Args:
            chat_ids: Список доступных ID чатов.
            arg: Аргумент команды ("all" или конкретный chat_id).

        Returns:
            Список целевых chat_id. Пустой список, если аргумент неверный или чат не найден.
        """
        arg_lower = arg.strip().lower()
        if arg_lower == "all":
            return list(chat_ids)

        try:
            requested_chat_id = int(arg_lower)
            if requested_chat_id in chat_ids:
                return [requested_chat_id]
            return []
        except ValueError:
            return []

    async def get_chat_list_for_display(
        self,
    ) -> CommandResult:
        """Получает список чатов для отображения.

        Returns:
            Результат с форматированным сообщением списка чатов.
        """
        if self._chats is None:
            return CommandResult(
                success=False,
                message="❌ Репозиторий чатов не инициализирован",
            )

        try:
            chat_ids = await self.list_chat_ids()
            if not chat_ids:
                return CommandResult(
                    success=True,
                    message="📭 Нет активных чатов для отправки",
                )

            # Если есть chat_info_service, получаем информацию о чатах
            if self._chat_info_service:
                chat_infos: list[ChatInfo] = []
                for chat_id in chat_ids:
                    try:
                        _chat_id, title = await self._chat_info_service.get_chat_info_safe(chat_id)
                        chat_infos.append(ChatInfo(chat_id=chat_id, title=title))
                    except Exception:
                        chat_infos.append(ChatInfo(chat_id=chat_id, title=None))

                # Используем билдер для форматирования
                from app.admin_notification_builders import AdminNotificationBuilders

                message = AdminNotificationBuilders.build_chat_list_message(chat_infos)
            else:
                # Простое форматирование без информации о чатах
                chat_list = [f"• Чат (ID: {chat_id})" for chat_id in chat_ids]
                message = (
                    "📋 Активные чаты для отправки:\n\n"
                    + "\n".join(chat_list)
                    + "\n\n"
                    + "💡 Использование:\n"
                    + "• /force_send <chat_id> — отправить жабу в указанный чат\n"
                    + "• /force_send all — отправить жабу во все чаты"
                )

            return CommandResult(success=True, message=message)
        except ServiceError as e:
            self.logger.error(
                f"Ошибка при получении списка чатов: {e}",
                event="get_chat_list_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при получении списка чатов: {str(e)[:200]}",
            )

    async def execute_force_send(
        self,
        requester_user_id: int,
        target_arg: str,
    ) -> CommandResult:
        """Выполняет принудительную отправку жабы.

        Инкапсулирует всю бизнес-логику:
        - Определение целевых чатов
        - Проверка лимитов
        - Генерация/fallback
        - Отправка в чаты
        - Форматирование результата

        Args:
            requester_user_id: ID пользователя, запрашивающего отправку.
            target_arg: Аргумент команды ("all" или конкретный chat_id).

        Returns:
            Результат выполнения команды с форматированным сообщением.

        Raises:
            ServiceError: Если необходимые сервисы не инициализированы.
        """
        # Проверяем наличие необходимых сервисов
        if self._chats is None:
            raise ServiceError("Репозиторий чатов не инициализирован")
        if self._image_service is None:
            raise ServiceError("Сервис изображений не инициализирован")
        if self._dispatch_delivery_service is None:
            raise ServiceError("Сервис отправки изображений не инициализирован")

        try:
            # Получаем список активных чатов
            chat_ids = await self.list_chat_ids()
            if not chat_ids:
                return CommandResult(
                    success=False,
                    message="📭 Нет активных чатов для отправки",
                )

            # Определяем целевые чаты
            target_chat_ids = AdminCommandService.determine_target_chats(chat_ids, target_arg)
            if not target_chat_ids:
                return CommandResult(
                    success=False,
                    message="❌ Неверный аргумент. Используйте: /force_send <chat_id> или /force_send all",
                )

            # Проверяем лимиты генераций (если сервис доступен)
            can_generate = True
            if self._frog_limit_service:
                # Для force_send проверяем только глобальный лимит, без per-user
                # Используем внутренний метод проверки лимитов через usage
                if self._usage:
                    can_generate = await self._usage.can_use_frog()

            # Генерируем или получаем изображение
            image_data: bytes | None = None
            caption: str = ""
            use_fallback = False

            if can_generate:
                try:
                    image_data, caption = await self._image_service.generate_frog_image(
                        user_id=requester_user_id,
                    )
                    # Увеличиваем счетчик использования только если генерация успешна
                    if self._usage:
                        await self._usage.increment(1)
                except Exception as e:
                    # Ошибка генерации - используем fallback
                    self.logger.warning(
                        f"Ошибка при генерации изображения, используем fallback: {e}",
                        event="force_send_generation_error",
                        status="warning",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                    use_fallback = True
            else:
                use_fallback = True
                self.logger.info("Лимит генераций исчерпан, используем fallback")

            # Если нужно использовать fallback и изображение еще не получено
            if use_fallback and image_data is None:
                fallback_image = await self._image_service.get_random_saved_image()
                if fallback_image:
                    image_data, caption = fallback_image
                    self.logger.info("Используется случайное изображение из архива")
                else:
                    self.logger.warning("Нет сохраненных изображений для отправки")
                    return CommandResult(
                        success=False,
                        message="❌ Не удалось получить изображение (лимит исчерпан и нет сохраненных изображений)",
                    )

            if not image_data:
                return CommandResult(
                    success=False,
                    message="❌ Не удалось получить изображение для отправки",
                )

            # Отправляем в чаты через dispatch_delivery_service
            delivery_result = await self._dispatch_delivery_service.send_to_multiple_chats(
                chat_ids=target_chat_ids,
                image_data=image_data,
                caption=caption,
            )
            # Устанавливаем флаг used_fallback в результат
            delivery_result.used_fallback = use_fallback

            # Форматируем результат
            from app.admin_notification_builders import AdminNotificationBuilders

            result_message = AdminNotificationBuilders.build_force_send_result_message(
                delivery_result=delivery_result,
                used_fallback=use_fallback,
            )

            return CommandResult(success=True, message=result_message)
        except ServiceError:
            raise
        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при выполнении force_send: {e}",
                event="force_send_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return CommandResult(
                success=False,
                message=f"❌ Ошибка при выполнении отправки: {str(e)[:200]}",
            )
