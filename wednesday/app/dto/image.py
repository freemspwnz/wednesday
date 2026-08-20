from dataclasses import dataclass
from typing import Self

from domain.image import Image


@dataclass(frozen=True, slots=True)
class ImageCard:
    """Snapshot of an image for sending to Telegram (photo + inline buttons)."""

    id: str
    file_id: str
    likes: int
    dislikes: int

    @classmethod
    def from_domain(cls, image: Image) -> Self:
        return cls(
            id=str(image.id),
            file_id=str(image.file_id),
            likes=image.rating.likes,
            dislikes=image.rating.dislikes,
        )
