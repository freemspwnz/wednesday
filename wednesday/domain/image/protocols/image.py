from typing import Protocol, runtime_checkable

from ..image import Image
from ..vo import ImageId, TelegramFileId


@runtime_checkable
class ImageRepo(Protocol):
    """Catalog image repository."""

    async def get_by_id(self, image_id: ImageId) -> Image | None:
        """Get image by id."""
        ...

    async def save(self, image: Image) -> None:
        """Persist image aggregate."""
        ...

    async def exists_by_telegram_file_id(self, file_id: TelegramFileId) -> bool:
        """Whether catalog already has this Telegram file id."""
        ...

    async def get_by_telegram_file_id(self, file_id: TelegramFileId) -> Image | None:
        """Lookup image by Telegram file id."""
        ...
