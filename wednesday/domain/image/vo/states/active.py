from dataclasses import dataclass

from .base import ImageState


@dataclass(frozen=True)
class ActiveState(ImageState):
    """Image is visible for /random and generate fallback."""
