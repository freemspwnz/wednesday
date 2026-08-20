"""In-chat schedule management via inline keyboard."""

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.dto import ChatContext
from app.protocols import Logger, RequestScope

from ....messages import chat as chat_msg
from ...utils import run_callback_handler, run_message_handler, safe_callback_answer
from .actions import apply_action
from .data import ScheduleData
from .keyboard import build_main_kb
from .screens import close_menu, navigate, refresh_after_mutation

chat_schedule_router = Router(name="chat_schedule")

_NAV_ACTIONS = frozenset({"menu", "open", "hours", "mins", "rmlist"})
_MUTATE_ACTIONS = frozenset({"add", "status", "day", "tz", "rm"})


@chat_schedule_router.message(Command("schedule"))
async def cmd_schedule(
    message: Message,
    command: CommandObject,
    chat: ChatContext,
    logger: Logger,
) -> None:
    """Show schedule UI in groups; explain private limitation elsewhere."""

    async def _action() -> None:
        args = (command.args or "").split()
        if args and args[0].lower() in {"help", "?"}:
            await message.answer(chat_msg.SCHEDULE_USAGE)
            return
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            await message.answer(chat_msg.SCHEDULE_PRIVATE_ONLY)
            return
        await message.answer(
            chat_msg.SCHEDULE_MENU_TITLE,
            reply_markup=build_main_kb(chat),
        )

    await run_message_handler(message, logger, _action)


@chat_schedule_router.callback_query(ScheduleData.filter())
async def cb_schedule(
    callback: CallbackQuery,
    callback_data: ScheduleData,
    chat: ChatContext,
    bot: Bot,
    scope: RequestScope,
) -> None:
    """Navigate schedule menu and apply schedule mutations."""

    async def _action() -> None:
        if not isinstance(callback.message, Message):
            await safe_callback_answer(callback)
            return
        if callback.message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            await safe_callback_answer(callback, chat_msg.SCHEDULE_PRIVATE_ONLY, show_alert=True)
            return

        action = callback_data.action
        value = callback_data.value

        if action == "rmlist" and not chat.schedules:
            await safe_callback_answer(callback, chat_msg.SCHEDULE_NO_SLOTS, show_alert=True)
            return
        if action == "close":
            await close_menu(callback)
            return
        if action in _NAV_ACTIONS or (action == "clear" and value in {"ask", "no"}):
            await navigate(callback, chat, action, value)
            return
        if action in _MUTATE_ACTIONS or (action == "clear" and value == "yes"):
            updated = await apply_action(
                callback,
                bot,
                scope,
                chat,
                action=action,
                value=value,
            )
            await refresh_after_mutation(callback, updated)
            return
        await safe_callback_answer(callback)

    await run_callback_handler(callback, scope.logger, _action)
