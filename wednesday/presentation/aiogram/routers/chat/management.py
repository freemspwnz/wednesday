"""Chat lifecycle commands: /activate, /deactivate."""

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import ChatContext
from app.protocols import Logger, RequestScope

from ...filters import GroupChatFilter
from ...messages import chat as chat_msg
from ..utils import run_message_handler
from .mappers import resolve_chat_member

chat_management_router = Router(name="chat_management")


@chat_management_router.message(Command("activate"), GroupChatFilter())
async def cmd_activate(
    message: Message,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Enable broadcast for this chat (chat admins via domain policy)."""

    async def _action() -> None:
        at = message.date
        actor_id, actor_role = await resolve_chat_member(bot, message, chat)
        updated = await scope.chat_management_uc.activate(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            at=at,
        )
        await message.answer(chat_msg.format_schedule_context(updated))

    await run_message_handler(message, logger, _action)


@chat_management_router.message(Command("deactivate"), GroupChatFilter())
async def cmd_deactivate(
    message: Message,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
    logger: Logger,
) -> None:
    """Pause broadcast for this chat (chat admins via domain policy)."""

    async def _action() -> None:
        at = message.date
        actor_id, actor_role = await resolve_chat_member(bot, message, chat)
        updated = await scope.chat_management_uc.deactivate(
            chat_id=chat.id,
            actor_id=actor_id,
            actor_role=actor_role,
            at=at,
        )
        await message.answer(chat_msg.format_schedule_context(updated))

    await run_message_handler(message, logger, _action)
