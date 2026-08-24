"""Bot-layer routers: root router assembly."""

from .chat import chat_router
from .common import common_router
from .image import image_router
from .user import admin_router, user_router

__all__ = [
    "admin_router",
    "chat_router",
    "common_router",
    "image_router",
    "user_router",
]
