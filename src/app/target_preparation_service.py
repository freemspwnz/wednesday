"""Сервис для подготовки целевых чатов для рассылки."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared.base.base_service import BaseService
from shared.protocols import IChatsRepo, IDispatchRegistry


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
    ) -> None:
        """Инициализирует сервис подготовки целей.

        Args:
            chats_repo: Репозиторий чатов.
            dispatch_registry: Реестр отправок для проверки.
        """
        super().__init__()
        self._chats_repo = chats_repo
        self._dispatch_registry = dispatch_registry

    async def prepare_targets(
        self,
        main_chat_id: str | None,
        send_error_message: Callable[[str], Awaitable[None]],
    ) -> set[int]:
        """Подготавливает список целевых чатов для рассылки.

        Args:
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.
            send_error_message: Коллбек для отправки краткого сообщения об ошибке в основной чат.

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
            await send_error_message("Нет настроенных чатов для отправки")

        return targets

    async def is_already_dispatched_for_all(
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
    ) -> bool:
        """Проверяет, отправляли ли уже в этот слот во все целевые чаты.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.

        Returns:
            True, если уже отправлено во все чаты, иначе False.
        """
        for target_chat in targets:
            if not await self._dispatch_registry.is_dispatched(
                slot_date,
                slot_time,
                target_chat,
            ):
                return False
        return True
