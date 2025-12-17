"""Сервисы хранения данных."""

from services.infrastructure.storage.image_storage import ImageStorageService
from services.infrastructure.storage.prompt_storage import PromptStorageService

__all__ = ["ImageStorageService", "PromptStorageService"]
