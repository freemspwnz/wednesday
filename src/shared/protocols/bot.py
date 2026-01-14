"""Протоколы для работы с ботом."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from telegram import Bot


@runtime_checkable
class IHandlersRegistry(Protocol):
    """Протокол для регистраторов обработчиков бота.

    Используется для типизации регистраторов обработчиков в BotLifecycleMixin,
    что позволяет использовать разные реализации (BotHandlersRegistry, SupportBotHandlersRegistry)
    без прямой зависимости от конкретных классов.
    """

    def register_all(self) -> None:
        """Регистрирует все обработчики команд и событий бота."""
        ...


@runtime_checkable
class IChatValidator(Protocol):
    """Протокол для валидаторов доступа к чатам.

    Используется для типизации валидаторов доступа к чатам в BotLifecycleMixin,
    что позволяет использовать разные реализации без прямой зависимости от конкретных классов.
    """

    async def validate_chat_access(self, bot: Bot, chat_id: str | None) -> None:
        """Проверяет доступность чата для бота.

        Args:
            bot: Экземпляр Telegram бота для проверки доступа.
            chat_id: ID чата для проверки (может быть None).

        Raises:
            Exception: Если чат недоступен или произошла ошибка при проверке.
        """
        ...
