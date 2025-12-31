"""Сервис для подготовки целевых чатов для рассылки."""

from __future__ import annotations

from app.dispatch_targets_helper import are_all_dispatched, check_dispatch_status_batch
from shared.base.base_service import BaseService
from shared.protocols.dispatch import IDispatchRegistry
from shared.protocols.infrastructure import ILogger
from shared.protocols.messaging import IMessagingService
from shared.protocols.repositories import IChatsRepo


class TargetPreparationService(BaseService):
    """Сервис для подготовки целевых чатов для рассылки.

    Отвечает за:
    - Получение списка целевых чатов
    - Проверку, был ли уже выполнен dispatch для всех чатов
    - Валидацию целевых чатов
    """

    def __init__(
        self,
        chats_repo: IChatsRepo,
        dispatch_registry: IDispatchRegistry,
        messaging_service: IMessagingService,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис подготовки целей.

        Args:
            chats_repo: Репозиторий чатов.
            dispatch_registry: Реестр отправок для проверки.
            messaging_service: Сервис отправки сообщений.
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._chats_repo = chats_repo
        self._dispatch_registry = dispatch_registry
        self._messaging = messaging_service

    async def prepare_targets(
        self,
        main_chat_id: str | None,
    ) -> set[int]:
        """Подготавливает список целевых чатов для рассылки.

        Args:
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.

        Returns:
            Множество ID целевых чатов. Пустое множество, если нет чатов для отправки.
        """
        targets: set[int] = set(await self._chats_repo.list_chat_ids() or [])
        if main_chat_id:
            try:
                chat_id_int: int = int(str(main_chat_id))
                targets.add(chat_id_int)
            except (ValueError, TypeError):
                pass

        if not targets:
            self.logger.warning("Нет целевых чатов для отправки сообщения")
            if main_chat_id:
                try:
                    main_chat_id_int = int(str(main_chat_id))
                    error_message = "⚠️ Нет настроенных чатов для отправки\nПопробуем в следующий раз! 🐸"
                    await self._messaging.send_message(
                        chat_id=main_chat_id_int,
                        text=error_message,
                    )
                except (ValueError, TypeError):
                    pass

        return targets

    async def is_already_dispatched_for_all(
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
    ) -> bool:
        """Проверяет, отправляли ли уже в этот слот во все целевые чаты.

        Использует batch-проверку для оптимизации (один запрос вместо N).

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.

        Returns:
            True, если уже отправлено во все чаты, иначе False.
        """
        if not targets:
            return True  # Пустое множество считается "все отправлено"

        status_map = await check_dispatch_status_batch(
            dispatch_registry=self._dispatch_registry,
            slot_date=slot_date,
            slot_time=slot_time,
            chat_ids=targets,
        )

        return are_all_dispatched(status_map)
