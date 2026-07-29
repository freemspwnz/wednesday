from dataclasses import dataclass
from typing import Self

from domain.image import Image, ImageId, ImageRating, TelegramFileId


@dataclass(frozen=True, slots=True)
class ImageCard:
    """Snapshot of an image for sending to Telegram (photo + inline buttons)."""

    id: ImageId
    file_id: TelegramFileId
    rating: ImageRating

    @classmethod
    def from_domain(cls, image: Image) -> Self:
        return cls(
            id=image.id,
            file_id=image.file_id,
            rating=image.rating,
        )
