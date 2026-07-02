from __future__ import annotations

from dataclasses import dataclass

from domain.image import Image, ImageId, TelegramFileId


@dataclass(frozen=True, slots=True)
class ImageCard:
    """Snapshot of an image for sending to Telegram (photo + inline buttons)."""

    id: ImageId
    file_id: TelegramFileId
    score: int

    @classmethod
    def from_domain(cls, image: Image) -> ImageCard:
        return cls(
            id=image.id,
            file_id=image.file_id,
            score=image.score,
        )
