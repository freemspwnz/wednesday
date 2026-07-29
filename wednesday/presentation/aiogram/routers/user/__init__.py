from aiogram import Router

from .admin import admin_router
from .model import (
    cmd_list_models,
    cmd_set_model,
    cmd_set_model_usage,
    model_router,
)
from .profile import cmd_me, profile_router

user_router = Router(name="user")

user_router.include_router(profile_router)
user_router.include_router(model_router)
user_router.include_router(admin_router)

__all__ = [
    "admin_router",
    "cmd_list_models",
    "cmd_me",
    "cmd_set_model",
    "cmd_set_model_usage",
    "user_router",
]
