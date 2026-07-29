from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import UserContext

from ...messages import user as user_msg

profile_router = Router(name="profile")


@profile_router.message(Command("me"))
async def cmd_me(message: Message, user: UserContext) -> None:
    """Show caller role, subscription, model, and ban status from registration context."""
    await message.answer(text=user_msg.format_me(user))
