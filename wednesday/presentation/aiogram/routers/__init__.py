"""Bot-layer routers: root router assembly."""

from .admin import admin_router
from .chat import chat_router
from .common import common_router
from .error import error_handler
from .image import image_router
from .user import user_router

__all__ = [
    "admin_router",
    "chat_router",
    "common_router",
    "error_handler",
    "image_router",
    "user_router",
]
