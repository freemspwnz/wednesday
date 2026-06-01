"""Bot-layer routers: root router assembly."""

from __future__ import annotations

from aiogram import Router

from .admin import admin_router
from .chat_event import chat_event_router
from .common import common_router
from .error import error_handler
from .image import image_router
from .user import user_router

__all__ = [
    "Router",
    "admin_router",
    "chat_event_router",
    "common_router",
    "error_handler",
    "image_router",
    "user_router",
]
