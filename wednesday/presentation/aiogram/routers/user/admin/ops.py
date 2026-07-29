"""Admin ops stubs (status / force_send / list_chats)."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ....messages import common as common_msg

ops_router = Router(name="ops")


@ops_router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Extended bot status (admin)."""
    await message.answer(common_msg.WIP)


@ops_router.message(Command("force_send"))
async def cmd_force_send(message: Message) -> None:
    """Force-send to chat(s) or list chats (admin)."""
    await message.answer(common_msg.WIP)


@ops_router.message(Command("list_chats"))
async def cmd_list_chats(message: Message) -> None:
    """List active chats (admin)."""
    await message.answer(common_msg.WIP)
