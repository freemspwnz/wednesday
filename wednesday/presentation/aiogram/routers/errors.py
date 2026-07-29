from aiogram import Bot
from aiogram.types import ErrorEvent, Update

from app.exceptions import unwrap_exception
from app.protocols import Logger

from ..messages.exceptions import SERVER_ERROR, user_message_for_exception


def _safe_update_log_context(update: Update) -> dict[str, object]:
    """Log-safe update snapshot without message text or other PII-heavy fields."""
    ctx: dict[str, object] = {"update_id": update.update_id}
    if update.message is not None:
        ctx["message_chat_id"] = update.message.chat.id
        if update.message.from_user is not None:
            ctx["message_from_user_id"] = update.message.from_user.id
    if update.edited_message is not None:
        ctx["edited_message_chat_id"] = update.edited_message.chat.id
    if update.my_chat_member is not None:
        ctx["my_chat_member_chat_id"] = update.my_chat_member.chat.id
        ctx["my_chat_member_status"] = update.my_chat_member.new_chat_member.status
    if update.chat_member is not None:
        ctx["chat_member_chat_id"] = update.chat_member.chat.id
        ctx["chat_member_status"] = update.chat_member.new_chat_member.status
    return ctx


async def error_handler(
    event: ErrorEvent,
    bot: Bot,  # aiogram injects Bot into error handlers
    logger: Logger,
) -> None:
    log = logger.bind(module="error_handler")
    root = unwrap_exception(event.exception)
    update = event.update

    user_text = user_message_for_exception(root)
    if user_text is not None:
        log.warning(
            "Handled application/domain error in update",
            error_type=type(root).__name__,
            error=str(root),
        )
        await send_text_to_update(update, user_text)
        return

    log.critical(
        "Critical error caused by update",
        error_type=type(root).__name__,
        error=str(root),
        exc_info=root,
        **_safe_update_log_context(update),
    )
    await send_text_to_update(update, SERVER_ERROR)


async def send_text_to_update(update: Update, text: str) -> bool:
    """Deliver user-facing text for a message update. Returns True if sent."""
    if update.message is not None:
        await update.message.answer(text)
        return True
    return False
