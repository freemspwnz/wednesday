from __future__ import annotations

from dataclasses import dataclass

from domain.image import Image, ImageId


@dataclass(frozen=True, slots=True)
class ImageCard:
    """Snapshot of an image for sending to Telegram (photo + inline buttons)."""

    id: ImageId
    file_id: str | None
    score: int

    @classmethod
    def from_domain(cls, image: Image) -> ImageCard:
        return cls(
            id=image.id,
            file_id=str(image.file_id) if image.file_id is not None else None,
            score=image.score,
        )
