"""Image catalog reset router."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.dto import ChatContext
from app.protocols import RequestScope

from ....messages import image as image_msg
from ...utils import run_callback_handler, run_message_handler
from .data import ResetViewsData

reset_router = Router(name="reset")


@reset_router.message(Command("reset"))
async def cmd_reset(
    message: Message,
    scope: RequestScope,
) -> None:
    """Ask the user to confirm catalog view reset."""

    async def _action() -> None:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Да",
                        callback_data=ResetViewsData(confirm=True).pack(),
                    ),
                    InlineKeyboardButton(
                        text="Отмена",
                        callback_data=ResetViewsData(confirm=False).pack(),
                    ),
                ],
            ],
        )
        await message.answer(image_msg.RESET_CONFIRM_PROMPT, reply_markup=markup)

    await run_message_handler(message, scope.logger, _action)


@reset_router.callback_query(ResetViewsData.filter())
async def cb_reset_views(
    callback: CallbackQuery,
    callback_data: ResetViewsData,
    chat: ChatContext,
    scope: RequestScope,
) -> None:
    """Confirm or cancel catalog view reset."""

    async def _action() -> None:
        if not isinstance(callback.message, Message):
            return
        if callback_data.confirm:
            count = await scope.image_catalog_uc.reset_views(chat_id=chat.id)
            await callback.message.edit_text(image_msg.RESET_DONE.format(count=count))
        else:
            await callback.message.edit_text(image_msg.RESET_CANCELLED)
        await callback.answer()

    await run_callback_handler(callback, scope.logger, _action)
