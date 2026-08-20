from aiogram import Router

from .ban import (
    ban_router,
    cmd_ban,
    cmd_ban_usage,
    cmd_unban,
    cmd_unban_usage,
)
from .mod import (
    cmd_demote,
    cmd_demote_usage,
    cmd_list_mods,
    cmd_promote,
    cmd_promote_usage,
    mod_router,
)
from .ops import (
    cmd_force_send,
    cmd_list_chats,
    cmd_status,
    ops_router,
)

admin_router = Router(name="admin")
admin_router.include_router(ban_router)
admin_router.include_router(mod_router)
admin_router.include_router(ops_router)

__all__ = [
    "admin_router",
    "cmd_ban",
    "cmd_ban_usage",
    "cmd_demote",
    "cmd_demote_usage",
    "cmd_force_send",
    "cmd_list_chats",
    "cmd_list_mods",
    "cmd_promote",
    "cmd_promote_usage",
    "cmd_status",
    "cmd_unban",
    "cmd_unban_usage",
]
