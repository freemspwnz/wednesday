from aiogram import Router

from .chat_member import chat_member_router, on_chat_member, on_my_chat_member
from .management import chat_management_router, cmd_activate, cmd_deactivate
from .schedule import cb_schedule, chat_schedule_router, cmd_schedule

chat_router = Router(name="chat")
chat_router.include_router(chat_member_router)
chat_router.include_router(chat_management_router)
chat_router.include_router(chat_schedule_router)

__all__ = [
    "cb_schedule",
    "chat_management_router",
    "chat_member_router",
    "chat_router",
    "chat_schedule_router",
    "cmd_activate",
    "cmd_deactivate",
    "cmd_schedule",
    "on_chat_member",
    "on_my_chat_member",
]
