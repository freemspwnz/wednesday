from aiogram import Router

from .chat_member import chat_member_router, on_chat_member, on_my_chat_member
from .management import chat_management_router, cmd_activate, cmd_deactivate
from .schedule import (
    chat_schedule_router,
    cmd_schedule,
    cmd_schedule_add,
    cmd_schedule_add_usage,
    cmd_schedule_clear,
    cmd_schedule_day,
    cmd_schedule_day_usage,
    cmd_schedule_remove,
    cmd_schedule_remove_usage,
    cmd_schedule_tz,
    cmd_schedule_tz_usage,
)

chat_router = Router(name="chat")
chat_router.include_router(chat_member_router)
chat_router.include_router(chat_management_router)
chat_router.include_router(chat_schedule_router)

__all__ = [
    "chat_management_router",
    "chat_member_router",
    "chat_router",
    "chat_schedule_router",
    "cmd_activate",
    "cmd_deactivate",
    "cmd_schedule",
    "cmd_schedule_add",
    "cmd_schedule_add_usage",
    "cmd_schedule_clear",
    "cmd_schedule_day",
    "cmd_schedule_day_usage",
    "cmd_schedule_remove",
    "cmd_schedule_remove_usage",
    "cmd_schedule_tz",
    "cmd_schedule_tz_usage",
    "on_chat_member",
    "on_my_chat_member",
]
